from pathlib import Path
import sys

APP_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent.parent)
YILIAO_SESSION_FILE = APP_DIR / "session.json"
LSB_SESSION_FILE = APP_DIR / "料商宝会话.json"
ARTICLE_MAP_FILE = APP_DIR / "多平台文章映射.json"
YILIAO_URLS = {
    "login": "https://yapi.njyuelu.cn/mgr/mgr/login",
    "publish": "https://yapi.njyuelu.cn/plan/mgr-do/add",
    "sync": "https://yapi.njyuelu.cn/plan/mgr-do/planSynAdd",
    "modify": "https://yapi.njyuelu.cn/plan/mgr-do/modifyContent",
    "sync_update": "https://yapi.njyuelu.cn/plan/mgr-do/planSynUpdate",
    "upload": "https://yapi.njyuelu.cn/resource/rse-img-do/uploads",
    "user_info": "https://yapi.njyuelu.cn/mgr/sys-user-do/userInfo",
}
LSB_BASE_URL = "https://qwer.lszs.red/lsb"
