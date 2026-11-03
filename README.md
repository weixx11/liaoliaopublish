# 料料统一小助手

在 Windows 桌面统一发布和编辑壹料、料商宝文章。

## 功能

- 分别登录壹料和料商宝，按需选择发布平台。
- 统一填写标题、副标题、免费内容、正文、价格和标签。
- 支持选择本地图片或从剪贴板粘贴图片。料商宝支持多张图片。
- 按标题或平台文章 ID 查找本地发布记录，追加内容、调整价格或操作置顶。
- 发布壹料文章时可选择同步的子账号。

## 使用便携版

完整解压便携版 ZIP，运行 `料料统一小助手.exe`。首次使用请登录所需平台。复制到其他电脑时请保留整个解压目录。

## 从源码运行

项目使用 Windows 上的 Conda `quant312` 环境和 Python 3.12。

```powershell
conda activate quant312
python -m pip install -r requirements-build.txt
python run_publisher.py
```

## 打包

在项目目录的 PowerShell 中运行：

```powershell
.\build_exe.ps1
```

打包脚本使用本机的 `quant312` Python。若 Conda 安装路径不同，请先调整脚本中的 Python 路径。构建完成后，在 `dist` 中获取便携版 ZIP。

登录会话和文章映射保存在程序目录。提交代码或分享便携版时，请排除本机生成的会话文件和文章记录。
