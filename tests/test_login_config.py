import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from publisher_app import login_config
from publisher_app.platforms.liaoxiaobao import LiaoxiaobaoPlatform


class LoginDefaultsTests(unittest.TestCase):
    def test_template_creation_and_existing_config_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'login.json'
            with patch.object(login_config,'LOGIN_CONFIG_FILE',path):
                initial = login_config.load_login_defaults()
                self.assertEqual(initial['料商宝监控']['密码'],'')
                path.write_text(json.dumps({'料商宝监控':{'账号':'monitor','密码':'test-password'},'料小宝监控':{'账号':'','密码':''}},ensure_ascii=False),encoding='utf-8-sig')
                original = path.read_bytes()
                values = login_config.load_login_defaults()
                self.assertEqual(values['料商宝监控']['账号'],'monitor')
                self.assertEqual(values['料商宝发布']['账号'],'')
                self.assertEqual(path.read_bytes(),original)

    def test_lxb_uses_same_session_and_saves_login_cookies(self):
        with patch('publisher_app.platforms.liaoxiaobao.load_session',return_value={}):
            platform = LiaoxiaobaoPlatform()
        def bootstrap(session):
            self.assertIs(session,platform.session)
            session.cookies.set('session-cookie','test')
            return 'secret','iv'
        with patch('publisher_app.platforms.liaoxiaobao.bootstrap',side_effect=bootstrap), patch('publisher_app.platforms.liaoxiaobao.login',return_value={'code':200,'data':{'token':'token'}}) as login, patch('publisher_app.platforms.liaoxiaobao.save_session') as save:
            platform.login('phone','password')
            self.assertIs(login.call_args.args[0],platform.session)
            self.assertEqual(save.call_args.args[1]['cookies'],{'session-cookie':'test'})


if __name__ == '__main__': unittest.main()
