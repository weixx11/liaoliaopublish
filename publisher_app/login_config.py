"""User-edited login defaults. Never copied into distributable builds."""
import json
from .config import APP_DIR

LOGIN_CONFIG_FILE = APP_DIR / '登录配置.local.json'
TEMPLATE = {
    '_说明': '仅用于填充登录框，不会自动登录。密码以明文保存，请勿分享此文件。料商宝发布与监控账号可以分别填写。',
    '壹料发布': {'账号':'', '密码':''},
    '料商宝发布': {'账号':'', '密码':''},
    '料小宝发布': {'账号':'', '密码':''},
    '料小宝监控': {'账号':'', '密码':''},
    '料商宝监控': {'账号':'', '密码':''},
}


def load_login_defaults():
    if not LOGIN_CONFIG_FILE.exists():
        try:
            with LOGIN_CONFIG_FILE.open('x',encoding='utf-8') as stream:
                json.dump(TEMPLATE,stream,ensure_ascii=False,indent=2)
        except FileExistsError:
            pass
    with LOGIN_CONFIG_FILE.open(encoding='utf-8-sig') as stream:
        data = json.load(stream)
    if not isinstance(data,dict):
        raise ValueError('登录配置最外层必须是JSON对象')
    if '料小宝监控' not in data:
        data['料小宝监控'] = {'账号':'','密码':''}
        with LOGIN_CONFIG_FILE.open('w',encoding='utf-8') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2)
    result = {}
    for key in TEMPLATE:
        if key.startswith('_'): continue
        entry = data.get(key,{})
        if not isinstance(entry,dict): raise ValueError(f'{key}配置必须是JSON对象')
        result[key] = {field:str(entry.get(field,'') or '') for field in ('账号','密码')}
    return result
