# 使用

## 引入

```python
import easytrader
```

## 设置同花顺客户端类型

**通用同花顺客户端**

```python
user = easytrader.use('universal_client') 
```

注: 通用同花顺客户端是指同花顺官网提供的客户端软件内的下单程序，内含对多个券商的交易支持，适用于券商不直接提供同花顺客户端时的后备方案。

**其他券商专用同花顺客户端**

```python
user = easytrader.use('ths')
```

注: 其他券商专用同花顺客户端是指对应券商官网提供的基于同花顺修改的软件版本，类似银河的双子星(同花顺版本)，国金证券网上交易独立下单程序（核新PC版）等。


**雪球组合**

```python
user = easytrader.use('xq')
```

**国金客户端**

```python
user = easytrader.use('gj_client') 
```

**海通客户端**

```python
user = easytrader.use('htzq_client')
```

**华泰客户端**

```python
user = easytrader.use('ht_client')
```


## 启动并连接客户端

### （一）其他券商专用同花顺客户端

其他券商专用同花顺客户端不支持自动登录，需要先手动登录。

请手动打开并登录客户端后，运用connect函数连接客户端。

```python
user.connect(r'客户端xiadan.exe路径') # 类似 r'C:\htzqzyb2\xiadan.exe'
```

### （二）通用同花顺客户端

需要先手动登录一次：添加券商，填入账户号、密码、验证码，勾选“保存密码”

第一次登录后，上述信息被缓存，可以调用prepare函数自动登录（仅需账户号、客户端路径，密码随意输入）。

### （三）其它

非同花顺的客户端，可以调用prepare函数自动登录。

调用prepare时所需的参数，可以通过`函数参数` 或 `配置文件` 赋予。

**1. 函数参数(推荐)**

```
user.prepare(user='用户名', password='雪球、银河客户端为明文密码', comm_password='华泰通讯密码，其他券商不用')
```

注: 雪球比较特殊，见下列配置文件格式

**2. 配置文件**

```python
user.prepare('/path/to/your/yh_client.json')  # 配置文件路径
```

注: 配置文件需自己用编辑器编辑生成, **请勿使用记事本**, 推荐使用 [notepad++](https://notepad-plus-plus.org/zh/) 或者 [sublime text](http://www.sublimetext.com/) 。

**配置文件格式如下：**

银河/国金客户端

```
{
  "user": "用户名",
  "password": "明文密码"
}

```

华泰客户端

```
{
   "user": "华泰用户名",
   "password": "华泰明文密码",
   "comm_password": "华泰通讯密码"
}

```

雪球

```
{
  "cookies": "雪球 cookies，登陆后获取，获取方式见 https://smalltool.github.io/2016/08/02/cookie/",
  "portfolio_code": "组合代码(例:ZH818559)",
  "portfolio_market": "交易市场(例:us 或者 cn 或者 hk)"
}
```

## 交易相关

有些客户端无法通过默认方法输入文本，可以通过开启 type_keys 的方法绕过，开启方式

```python
user.enable_type_keys_for_editor()
```

###  获取资金状况

```python
user.balance

# return
[{'参考市值': 21642.0,
  '可用资金': 28494.21,
  '币种': '0',
  '总资产': 50136.21,
  '股份参考盈亏': -90.21,
  '资金余额': 28494.21,
  '资金帐号': 'xxx'}]
```

### 获取持仓

```python
user.position

# return
[{'买入冻结': 0,
  '交易市场': '沪A',
  '卖出冻结': '0',
  '参考市价': 4.71,
  '参考市值': 10362.0,
  '参考成本价': 4.672,
  '参考盈亏': 82.79,
  '当前持仓': 2200,
  '盈亏比例(%)': '0.81%',
  '股东代码': 'xxx',
  '股份余额': 2200,
  '股份可用': 2200,
  '证券代码': '601398',
  '证券名称': '工商银行'}]
```

### 买入

```python
user.buy('162411', price=0.55, amount=100)

# return
{'entrust_no': 'xxxxxxxx'}
```

注: 系统可以配置是否返回成交回报。如果没配的话默认返回 `{"message": "success"}`

### 卖出

```python
user.sell('162411', price=0.55, amount=100)

# return
{'entrust_no': 'xxxxxxxx'}
```


### 撤单

```python
user.cancel_entrust('buy/sell 获取的 entrust_no')

# return
{'message': 'success'}
```

### 查询当日成交

```python
user.today_trades

# return
[{'买卖标志': '买入',
  '交易市场': '深A',
  '委托序号': '12345',
  '成交价格': 0.626,
  '成交数量': 100,
  '成交日期': '20170313',
  '成交时间': '09:50:30',
  '成交金额': 62.60,
  '股东代码': 'xxx',
  '证券代码': '162411',
  '证券名称': '华宝油气'}]
```

### 查询当日委托

```python
user.today_entrusts

# return
[{'买卖标志': '买入',
  '交易市场': '深A',
  '委托价格': 0.627,
  '委托序号': '111111',
  '委托数量': 100,
  '委托日期': '20170313',
  '委托时间': '09:50:30',
  '成交数量': 100,
  '撤单数量': 0,
  '状态说明': '已成',
  '股东代码': 'xxxxx',
  '证券代码': '162411',
  '证券名称': '华宝油气'},
 {'买卖标志': '买入',
  '交易市场': '深A',
  '委托价格': 0.6,
  '委托序号': '1111',
  '委托数量': 100,
  '委托日期': '20170313',
  '委托时间': '09:40:30',
  '成交数量': 0,
  '撤单数量': 100,
  '状态说明': '已撤',
  '股东代码': 'xxx',
  '证券代码': '162411',
  '证券名称': '华宝油气'}]
```


### 查询今日可申购新股

```python
from easytrader.utils.stock import get_today_ipo_data
get_today_ipo_data()

# return
[{'stock_code': '股票代码',
  'stock_name': '股票名称',
  'price': 发行价,
  'apply_code': '申购代码'}]
```

### 一键打新

```python
user.auto_ipo()
```

### 刷新数据

```python
user.refresh()
```

### 雪球组合比例调仓 

```python
user.adjust_weight('股票代码', 目标比例)
```

例如 `user.adjust_weight('000001', 10)`是将平安银行在组合中的持仓比例调整到10%。

## 退出客户端软件

```python
user.exit()
```

## 多账号管理（通用同花顺客户端）

在一个已登录多个券商账号的同花顺客户端中，通过 `AccountManager` 统一管理和切换。

### 初始化

```python
import easytrader

trader = easytrader.use('universal_client')
trader.connect(exe_path='C:\\同花顺软件\\同花顺\\xiadan.exe')

# 自动扫描已登录的账号（单账号时自动降级为直通模式）
am = easytrader.AccountManager(trader)
```

初始化时自动扫描当前已登录的券商账号，不需手动调用 `scan()`。

### 查看账号

```python
am.list()
# [1] 湘财证券 (ALT+1) ← 当前
# [2] 模拟炒股 (ALT+2)

am.current   # 从界面实时读取当前账号名称
am.active    # AccountManager 记录的当前账号
```

### 切换账号

```python
am.switch('湘财证券')          # 按名称切换
am.switch(0)                   # 按索引切换
am['模拟炒股'].balance         # 原子地切换并查询
```

切换通过发送 `ALT+数字` 快捷键实现。

### 并发安全调用

```python
am['湘财证券'].balance                    # 切到湘财查余额
am['模拟炒股'].position                   # 切到模拟盘查持仓
am['模拟炒股'].buy('162411', 0.55, 100)   # 切换和下单不可被其他线程或进程打断
```

同一个客户端的全部操作由 Windows 命名 Mutex 串行执行，同时覆盖多线程和多进程。
`am['账号']` 会在获得锁后切换并验证真实账号，再执行完整的查询、下单和弹窗处理。

并发场景不要将 `switch()` 和后续操作拆开：

```python
# 不安全：switch() 返回后其他线程或进程可能切换账号
am.switch('湘财证券')
am.buy('162411', 0.55, 100)
```

多账号模式会拒绝这种未显式指定账号的代理调用；单账号模式仍保持原有直通行为。

等待客户端锁超过 30 秒会抛出 `ClientBusyError`，不会继续执行已经过期的操作。

如果上一个进程在操作客户端时异常退出，或者交易/撤单操作抛出异常、被中断，
后续调用会抛出 `ClientStateUnknownError`。请先人工核对当日委托和客户端界面，
确认不会重复下单后再清除恢复标记：

```python
trader.clear_client_recovery_state(
    exe_path='C:\\同花顺软件\\同花顺\\xiadan.exe'
)
```

该方法只清除 easytrader 的恢复标记，不会撤单、补单或修改客户端内容。

### 重命名

```python
am.rename(0, '主力账户')
```

`name` 是自定义别名，`label` 保留界面扫描到的原始名称。`switch()` 同时匹配 `name` 和 `label`。

### 遍历所有账号

```python
for acc in am.accounts:
    bal = am[acc['name']].balance
    print(f"{acc['name']}: {bal['总资产']}")
```

### 完整示例

```python
import easytrader

trader = easytrader.use('universal_client')
trader.connect(exe_path='C:\\同花顺软件\\同花顺\\xiadan.exe')
# 某些客户端需要开启 type_keys 输入
trader.enable_type_keys_for_editor()

am = easytrader.AccountManager(trader)  # 自动扫描账号

# 重命名
am.rename(0, '湘财')
am.rename(1, '模拟盘')

# 原子地切换 + 操作
print('余额:', am['湘财'].balance)
print('持仓:', am['湘财'].position)

# 临时查另一个账号
am['模拟盘'].buy('162411', 0.55, 100)

# 遍历所有账号
for acc in am.accounts:
    total = am[acc['name']].balance.get('总资产', 0)
    print(f"{acc['name']}: {total}")
```

## 常见问题

### 验证码识别

easytrader 使用百度 OCR 自动识别同花顺弹出的验证码，详情见 [百度 OCR 使用说明](baidu_ocr.md)。

配置方式：在项目根目录创建 `baidu_ocr.json`：
```json
{"api_key": "你的API_Key", "secret_key": "你的Secret_Key"}
```

### 某些同花顺客户端不允许拷贝 `Grid` 数据

现在默认获取 `Grid` 数据的策略是通过剪切板拷贝，有些券商不允许这种方式，导致无法获取持仓等数据。为解决此问题，额外实现了一种通过将 `Grid` 数据存为文件再读取的策略，
使用方式如下:

```python
from easytrader import grid_strategies

user.grid_strategy = grid_strategies.Xls
```

### 通过工具栏刷新按钮刷新数据

当前的刷新数据方式是通过切换菜单栏实现，通用但是比较缓慢，可以选择通过点击工具栏的刷新按钮来刷新

```python
from easytrader import refresh_strategies

# refresh_btn_index 指的是刷新按钮在工具栏的排序，默认为第四个，根据客户端实际情况调整
user.refresh_strategy = refresh_strategies.Toolbar(refresh_btn_index=4)
```

### 无法保存对应的 xls 文件

有些系统默认的临时文件目录过长，使用 xls 策略时无法正常保存，可通过如下方式修改为自定义目录

```
user.grid_strategy_instance.tmp_folder = 'C:\\custom_folder'
```

### 如何关闭 debug 日志的输出

```python
user = easytrader.use('yh', debug=False)

```


# 编辑配置文件，运行后出现 `json` 解码报错


出现如下错误

```python
raise JSONDecodeError("Expecting value", s, err.value) from None

JSONDecodeError: Expecting value
```

请勿使用 `记事本` 编辑账户的 `json` 配置文件，推荐使用 [notepad++](https://notepad-plus-plus.org/zh/) 或者 [sublime text](http://www.sublimetext.com/)

