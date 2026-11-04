import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

module = importlib.import_module('多平台文章发布')


class ClipboardPasteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = module.UnifiedPublisher()
        cls.app.withdraw()
        cls.directory = tempfile.TemporaryDirectory()
        cls.picture = Path(cls.directory.name) / '微信 图片.png'
        Image.new('RGB',(2,2)).save(cls.picture)

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()
        cls.directory.cleanup()

    def test_text_path_and_uri_in_all_editors(self):
        for widget in (self.app.free,self.app.body,self.app.edit_body):
            for text in (str(self.picture),self.picture.as_uri()):
                with self.subTest(widget=widget,text=text):
                    widget.delete('1.0','end')
                    attachments = self.app._attachments_for(widget)
                    attachments.clear()
                    with patch.object(module.ImageGrab,'grabclipboard',return_value=None), patch.object(widget,'clipboard_get',return_value=text):
                        self.assertEqual(self.app.paste_image(None,widget),'break')
                    self.assertEqual(len(attachments),1)
                    self.assertEqual(Path(attachments[0][1]),self.picture)
                    self.assertNotIn(str(self.picture),widget.get('1.0','end'))
                    self.assertTrue(widget.bind('<<Paste>>'))

    def test_plain_text_falls_through_and_missing_image_is_blocked(self):
        widget = self.app.free
        for text,expected in (('普通文字',None),(str(self.picture.parent / 'missing.png'),'break')):
            with patch.object(module.ImageGrab,'grabclipboard',return_value=None), patch.object(widget,'clipboard_get',return_value=text):
                self.assertEqual(self.app.paste_image(None,widget),expected)

    def test_file_list_keeps_multiple_images(self):
        widget = self.app.body
        self.app.publish_images.clear()
        with patch.object(module.ImageGrab,'grabclipboard',return_value=[str(self.picture),str(self.picture)]):
            self.assertEqual(self.app.paste_image(None,widget),'break')
        self.assertEqual(len(self.app.publish_images),2)


if __name__ == '__main__':
    unittest.main()
