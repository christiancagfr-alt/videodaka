"""Google desktop OAuth with refresh tokens held in the native OS credential store."""
import hashlib
import json
import os

SERVICE='DevotionFlow Google OAuth'
# Use Google's canonical URI for the email scope. The short alias `email` is
# returned as `userinfo.email` by Google's token endpoint, which oauthlib treats
# as a scope change and rejects during the desktop OAuth callback.
SCOPES=['openid','https://www.googleapis.com/auth/userinfo.email','https://www.googleapis.com/auth/spreadsheets']
GOOGLE_SCOPE_ALIASES={'email':'https://www.googleapis.com/auth/userinfo.email'}

def normalize_scopes(scopes):
    if isinstance(scopes,str): scopes=scopes.split()
    return {GOOGLE_SCOPE_ALIASES.get(scope,scope) for scope in (scopes or [])}

def oauth_client_id(path):
    from pathlib import Path
    selected=Path(path).expanduser()
    if selected.stat().st_size>128*1024: raise ValueError('OAuth 桌面配置文件过大')
    with selected.open('r',encoding='utf-8-sig') as stream: data=json.load(stream)
    config=data.get('installed') if isinstance(data,dict) else None
    if not isinstance(config,dict) or not isinstance(config.get('client_id'),str) or not config['client_id'].endswith('.apps.googleusercontent.com'):
        raise ValueError('请选择 Google Cloud 中创建的桌面应用 OAuth JSON 文件')
    if not isinstance(config.get('client_secret'),str) or not config['client_secret'].strip(): raise ValueError('OAuth 桌面配置文件缺少 client_secret')
    if config.get('auth_uri')!='https://accounts.google.com/o/oauth2/auth' or config.get('token_uri')!='https://oauth2.googleapis.com/token':
        raise ValueError('OAuth 配置必须使用 Google 官方授权和令牌地址')
    return config['client_id']

def _key(client_id):
    return hashlib.sha256(client_id.encode('utf-8')).hexdigest()

def _store():
    import keyring
    backend=keyring.get_keyring()
    name=type(backend).__module__+'.'+type(backend).__name__
    allowed=('keyring.backends.Windows.WinVaultKeyring','keyring.backends.macOS.Keyring','keyring.backends.SecretService.Keyring')
    if name not in allowed:
        raise RuntimeError('未检测到安全的系统凭据库，请在 Windows 使用 Credential Locker，或在 macOS 使用钥匙串。')
    return keyring

def save_tokens(client_id, credentials):
    _store().set_password(SERVICE,_key(client_id),credentials.to_json())

def load_credentials(client_id):
    from google.oauth2.credentials import Credentials
    raw=_store().get_password(SERVICE,_key(client_id))
    if not raw: return None
    try: data=json.loads(raw)
    except (TypeError,json.JSONDecodeError):
        _store().delete_password(SERVICE,_key(client_id)); return None
    credentials=Credentials.from_authorized_user_info(data,SCOPES)
    if credentials.expired and credentials.refresh_token:
        from google.auth.transport.requests import Request
        credentials.refresh(Request()); save_tokens(client_id,credentials)
    return credentials

def login(client_file):
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow=InstalledAppFlow.from_client_secrets_file(client_file,SCOPES)
    # Google may return the documented `email` alias for the full userinfo
    # scope. oauthlib otherwise raises Warning before the app can verify grants.
    # Relax only for this isolated worker call; the granted scopes are checked
    # explicitly below, and the environment is restored immediately afterward.
    previous=os.environ.get('OAUTHLIB_RELAX_TOKEN_SCOPE')
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE']='1'
    try:
        credentials=flow.run_local_server(host='localhost',port=0,open_browser=True,
            authorization_prompt_message='正在打开默认浏览器进行 Google 授权…',
            success_message='Google 已返回授权结果。请回到 DevotionFlow 等待“已连接”确认，不要再次发起授权。若应用显示失败，再重试。',
            access_type='offline',prompt='consent',timeout_seconds=300)
    finally:
        if previous is None: os.environ.pop('OAUTHLIB_RELAX_TOKEN_SCOPE',None)
        else: os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE']=previous
    # `scopes` on google-auth Credentials is the requested scope list; use
    # `granted_scopes` when Google returned the actual list. An omitted list
    # means the server kept the requested scope under RFC 6749.
    actual_scopes=getattr(credentials,'granted_scopes',None)
    granted=normalize_scopes(actual_scopes if actual_scopes is not None else SCOPES)
    required=normalize_scopes(SCOPES)
    if not required.issubset(granted):
        raise RuntimeError('Google 登录已完成，但返回的授权范围不完整。请确认同意 Sheets 和邮箱权限后重试。')
    info=credentials.id_token
    email=''
    if isinstance(info,dict): email=info.get('email','')
    if not email:
        from google.auth.transport.requests import AuthorizedSession
        response=AuthorizedSession(credentials).get('https://openidconnect.googleapis.com/v1/userinfo',timeout=15)
        response.raise_for_status(); email=response.json().get('email','')
    oauth_client=flow.client_config['client_id']
    save_tokens(oauth_client,credentials)
    # Confirm the OS credential store can immediately return the token for this client.
    # The browser's success page is sent just before run_local_server returns, so it
    # must not be treated as an app-level connection confirmation by itself.
    stored=load_credentials(oauth_client)
    if stored is None or not stored.valid:
        raise RuntimeError('Google 已完成浏览器授权，但系统凭据库未能读取刚保存的登录令牌。请重新连接 Google 账号。')
    return oauth_client,email
