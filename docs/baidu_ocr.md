# 百度 OCR 验证码识别

easytrader 使用百度 OCR 作为验证码识别的默认方案。当同花顺客户端弹出验证码时，自动调用百度 OCR 识别并输入，无需手动操作。

## 免费额度

| 接口 | 免费额度 | 说明 |
|------|---------|------|
| 网络图片文字识别 | 1000次/月 | 首选接口，适合验证码 |
| 通用文字识别（标准版） | 1000次/月 | |
| 通用文字识别（标准含位置版） | 1000次/月 | |
| 通用文字识别（高精度版） | 1000次/月 | |
| 通用文字识别（高精度含位置版） | 500次/月 | |
| **合计** | **4500次/月** | 额度耗尽自动切换下一个接口 |

## 配置方式

### 1. 注册百度云账号

前往 [百度智能云控制台](https://console.bce.baidu.com/ai/#/ai/ocr/overview/index) 注册并登录。

### 2. 创建应用

- 在控制台左侧选择「文字识别」
- 点击「创建应用」，填写应用名称
- 创建成功后，在应用列表获取 `API Key` 和 `Secret Key`

### 3. 配置到项目

在项目根目录（即运行脚本的目录）创建 `baidu_ocr.json` 文件：

```json
{
  "api_key": "你的API_Key",
  "secret_key": "你的Secret_Key"
}
```

> `access_token` 会在首次使用时自动获取并写入同一文件，有效期内无需重复请求。

## 使用方法

配置好 `baidu_ocr.json` 后，无需任何额外代码。当触发验证码时自动调用百度 OCR 识别：

```python
import easytrader

user = easytrader.use('universal_client')
user.enable_type_keys_for_editor()
user.connect(r'C:\同花顺软件\同花顺\xiadan.exe')

# 自动触发验证码识别
position = user.position
```

手动调用：

```python
from easytrader.utils.captcha import captcha_recognize

result = captcha_recognize("captcha.png")
print(result)  # 例如: 'N5VK'
```

## 常见问题

### 提示「找不到配置文件」

请检查项目根目录是否存在 `baidu_ocr.json` 文件，确保文件名和路径正确。

### 提示「鉴权失败」

- 确认 `api_key` 和 `secret_key` 填写正确
- 确认百度云账号已实名认证
- 确认已开通文字识别服务

### 不想使用百度 OCR？

可手动输入验证码：

```python
from easytrader.utils.captcha import input_verify_code_manual
code = input_verify_code_manual("captcha.png")  # 弹出图片，手动输入
```
