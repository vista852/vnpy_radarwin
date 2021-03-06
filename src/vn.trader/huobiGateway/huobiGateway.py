# encoding: UTF-8

'''
vn.huobi的gateway接入

注意：
1. 该接口尚处于测试阶段，用于实盘请谨慎
2. 目前仅支持USD和CNY的现货交易，USD的期货合约交易暂不支持
'''
import hashlib
import json
import os
import urllib
from copy import copy
from datetime import datetime, time
from threading import Condition

import vnhuobi
from vtGateway import *
from radarwinFunction.rwConstant import *
from time import localtime
import talib as ta
# 价格类型映射
priceTypeMap = {}
priceTypeMap['buy'] = (DIRECTION_LONG, PRICETYPE_LIMITPRICE)
priceTypeMap['buy_market'] = (DIRECTION_LONG, PRICETYPE_MARKETPRICE)
priceTypeMap['sell'] = (DIRECTION_SHORT, PRICETYPE_LIMITPRICE)
priceTypeMap['sell_market'] = (DIRECTION_SHORT, PRICETYPE_MARKETPRICE)
priceTypeMapReverse = {v: k for k, v in priceTypeMap.items()} 

# 方向类型映射
directionMap = {}
directionMapReverse = {v: k for k, v in directionMap.items()}

# 委托状态印射
statusMap = {}
statusMap[-1] = STATUS_CANCELLED
statusMap[0] = STATUS_NOTTRADED
statusMap[1] = STATUS_PARTTRADED
statusMap[2] = STATUS_ALLTRADED
statusMap[4] = STATUS_UNKNOWN

############################################
## 交易合约代码
############################################

# USD
BTC_USD_SPOT = 'BTC_USD_SPOT'
BTC_USD_THISWEEK = 'BTC_USD_THISWEEK'
BTC_USD_NEXTWEEK = 'BTC_USD_NEXTWEEK'
BTC_USD_QUARTER = 'BTC_USD_QUARTER'

LTC_USD_SPOT = 'LTC_USD_SPOT'
LTC_USD_THISWEEK = 'LTC_USD_THISWEEK'
LTC_USD_NEXTWEEK = 'LTC_USD_NEXTWEEK'
LTC_USD_QUARTER = 'LTC_USD_QUARTER'

# CNY
BTC_CNY_SPOT = 'BTC_CNY_SPOT'
LTC_CNY_SPOT = 'LTC_CNY_SPOT'

# 印射字典
spotSymbolMap = {}
spotSymbolMap['ltc_usd'] = LTC_USD_SPOT
spotSymbolMap['btc_usd'] = BTC_USD_SPOT
spotSymbolMap['ltc_cny'] = LTC_CNY_SPOT
spotSymbolMap['btc_cny'] = BTC_CNY_SPOT
spotSymbolMapReverse = {v: k for k, v in spotSymbolMap.items()}


############################################
## Channel和Symbol的印射
############################################
channelSymbolMap = {}



# CNY
channelSymbolMap['btccny'] = BTC_CNY_SPOT
channelSymbolMap['ltccny'] = LTC_CNY_SPOT


############################################
## 交易所返回Response结构体
############################################
RESPONSE_CHANNEL = 'channel'
RESPONSE_DATE = 'date'
RESPONSE_NO = 'no'
RESPONSE_TICKER = 'ticker'
RESPONSE_ASKS='asks'

#持仓信息


############################################
## 持仓类型（BTC,LTC,CNY）
############################################
SYMBOL_STYLE=['BTC','LTC','CNY']

# 电子货币代码
SYMBOL_BTC = 'btc'
SYMBOL_LTC = 'ltc'


############################################
## 成交单类型
############################################
tradeTypeMap = {}

tradeTypeMap['1'] = TRADE_TYPE_LIMIT_BUY
tradeTypeMap['2'] = TRADE_TYPE_LIMIT_SELL
tradeTypeMap['3'] = TRADE_TYPE_MARKET_BUY
tradeTypeMap['4'] = TRADE_TYPE_MARKET_SELL

############################################
## 委托单类型
############################################
orderTypeMap = {}

orderTypeMap['1'] = ORDER_TYPE_BUY
orderTypeMap['2'] = ORDER_TYPE_SELL


########################################################################
class HuobiGateway(VtGateway):
    """Huobi接口"""

    #----------------------------------------------------------------------
    def __init__(self, eventEngine, gatewayName='HUOBI'):
        """Constructor"""
        super(HuobiGateway, self).__init__(eventEngine, gatewayName)
        
        self.api = Api(self)
        self.leverage = 0
        self.connected = False

        
    #----------------------------------------------------------------------
    def connect(self):
        """连接"""
        # 载入json文件
        fileName = self.gatewayName + '_connect.json'
        path = os.path.abspath(os.path.dirname(__file__))
        fileName = os.path.join(path, fileName)
        
        try:
            f = file(fileName)
        except IOError:
            log = VtLogData()
            log.gatewayName = self.gatewayName
            log.logContent = u'读取连接配置出错，请检查'
            self.onLog(log)
            return
        
        # 解析json文件
        setting = json.load(f)
        try:
            host = str(setting['host'])
            apiKey = str(setting['apiKey'])
            secretKey = str(setting['secretKey'])
            trace = setting['trace']
            leverage = setting['leverage']
            password=setting['password']
        except KeyError:
            log = VtLogData()
            log.gatewayName = self.gatewayName
            log.logContent = u'连接配置缺少字段，请检查'
            self.onLog(log)
            return            
        
        # 初始化接口
        self.leverage = leverage

        self.api.init(host, apiKey, secretKey, trace,password)
        
        log = VtLogData()
        log.gatewayName = self.gatewayName
        log.logContent = u'接口初始化成功'
        self.onLog(log)

        self.api.qryGenerateCnyContract()

        #self.api.getOrders()

        # self.api.getTickerInfo(SYMBOL_BTC)
        # self.api.getTickerInfo(SYMBOL_LTC)
        # self.api.getDepthInfo(SYMBOL_BTC)
        # self.api.getDepthInfo(SYMBOL_LTC)
        #self.api.qryOrders()
        #self.api.qryTrades()

        # 启动查询
        self.initQuery()
        #self.startQuery()
    
    #----------------------------------------------------------------------
    def subscribe(self, subscribeReq):
        """订阅行情"""
        pass
        
    #----------------------------------------------------------------------
    def cancelOrder(self, cancelOrderReq):
        """撤单"""
        self.api.cancelOrder(cancelOrderReq)
        
    #----------------------------------------------------------------------
    def qryAccount(self):
        """查询账户资金"""
        self.api.spotUserInfo()
        
    #----------------------------------------------------------------------
    def qryPosition(self):
        """查询持仓"""
        pass
    # ----------------------------------------------------------------------
    def qryOrders(self):
        """查询委托"""
        self.api.getOrders()

    #----------------------------------------------------------------------
    def qryTrades(self):
        """查询委托"""
        self.api.getTrades()

    # ----------------------------------------------------------------------
    def close(self):
        """关闭"""
        pass
        
    #----------------------------------------------------------------------
    def initQuery(self):
        """初始化连续查询"""
        if self.qryEnabled:
            # 需要循环的查询函数列表
            self.qryFunctionList = [self.qryAccount,self.qryOrders,self.qryTrades]
            
            self.qryCount = 0           # 查询触发倒计时
            self.qryTrigger = 2         # 查询触发点
            self.qryNextFunction = 0    # 上次运行的查询函数索引
            
            self.startQuery()  
    
    #----------------------------------------------------------------------
    def query(self, event):
        """注册到事件处理引擎上的查询函数"""
        self.qryCount += 1
        
        if self.qryCount > self.qryTrigger:
            # 清空倒计时
            self.qryCount = 0
            
            # 执行查询函数
            function = self.qryFunctionList[self.qryNextFunction]
            function()
            
            # 计算下次查询函数的索引，如果超过了列表长度，则重新设为0
            self.qryNextFunction += 1
            if self.qryNextFunction == len(self.qryFunctionList):
                self.qryNextFunction = 0
                
    #----------------------------------------------------------------------
    def startQuery(self):
        """启动连续查询"""
        self.eventEngine.register(EVENT_TIMER, self.query)
    
    #----------------------------------------------------------------------
    def setQryEnabled(self, qryEnabled):
        """设置是否要启动循环查询"""
        self.qryEnabled = qryEnabled

    # ----------------------------------------------------------------------
    def sendOrder(self, orderReq):
        """发单"""
        return self.api.sendOrder(orderReq)


########################################################################
class Api(vnhuobi.HuobiApi):
    """Huobi的API实现"""

    #----------------------------------------------------------------------
    def __init__(self, gateway):
        """Constructor"""
        super(Api, self).__init__()

        self.gateway = gateway                  # gateway对象
        self.gatewayName = gateway.gatewayName  # gateway对象名称

        self.cbDict = {}
        self.tickDict = {}
        self.orderDict = {}

        self.lastOrderID = ''
        self.orderCondition = Condition()
        self.trade_password = False

        #self.initCallback()


    #----------------------------------------------------------------------
    def qryInstruments(self):
            """查询合约"""
            params = {'accountId': self.accountId}
            self.getInstruments(params)

    # ----------------------------------------------------------------------

    def generateSpecificContract(self, contract, symbol):
        """生成合约"""
        new = copy(contract)
        new.symbol = symbol
        new.vtSymbol = symbol
        new.name = symbol
        return new

        # ----------------------------------------------------------------------

    def generateCnyContract(self):
        """生成CNY合约信息"""
        contractList = []

        contract = VtContractData()
        contract.exchange = EXCHANGE_HUOBI
        contract.productClass = PRODUCT_SPOT
        contract.size = 1
        contract.priceTick = 0.01

        contractList.append(self.generateSpecificContract(contract, BTC_CNY_SPOT))
        contractList.append(self.generateSpecificContract(contract, LTC_CNY_SPOT))

        return contractList


    def qryGenerateCnyContract(self):
        l = self.generateCnyContract()
        for contract in l:
            contract.gatewayName = self.gatewayName
            self.gateway.onContract(contract)

    # ----------------------------------------------------------------------
    def onMessage(self, ws, evt):
        """信息推送"""
        data=json.loads(evt)
        channel = data[RESPONSE_CHANNEL]
        callback = self.cbDict[channel]
        callback(data)
        
    #----------------------------------------------------------------------
    def onError(self, evt):
        """错误推送"""
        error = VtErrorData()
        error.gatewayName = self.gatewayName
        error.errorMsg = str(evt)
        self.gateway.onError(error)
        
    #----------------------------------------------------------------------
    def onClose(self, ws):
        """接口断开"""
        self.gateway.connected = True
        self.writeLog(u'服务器连接断开')

    #----------------------------------------------------------------------
    def onOpen(self, ws):
        pass

    #----------------------------------------------------------------------
    def writeLog(self, content):
        """快速记录日志"""
        log = VtLogData()
        log.gatewayName = self.gatewayName
        log.logContent = content
        self.gateway.onLog(log)
        
    #----------------------------------------------------------------------
    def initCallback(self):
        """初始化回调函数"""
        pass


    #----------------------------------------------------------------------
    def generateSpecificContract(self, contract, symbol):
        """生成合约"""
        new = copy(contract)
        new.symbol = symbol
        new.vtSymbol = symbol
        new.name = symbol
        return new

    #----------------------------------------------------------------------
    def generateCnyContract(self):
        """生成CNY合约信息"""
        contractList = []
        
        contract = VtContractData()
        contract.exchange = EXCHANGE_HUOBI
        contract.productClass = PRODUCT_SPOT
        contract.size = 1
        contract.priceTick = 0.01
        
        contractList.append(self.generateSpecificContract(contract, BTC_CNY_SPOT))

        return contractList

    # ----------------------------------------------------------------------
    # def getTickerInfo(self,symbol):
    #     """查询行情数据"""
    #     paramsDict = {"ticker_depth": 'ticker', "symbol": symbol}
    #     self.sendRequest(paramsDict, self.onTicker, API_FLAG_TICKER)

    # ----------------------------------------------------------------------
    def onTicker(self, data):
        """"""
        if 'ticker' not in data:
            return
        ticker = data['ticker']
        symbol = channelSymbolMap[ticker['symbol']]
        if symbol not in self.tickDict:
            tick = VtTickData()
            tick.symbol = symbol
            tick.vtSymbol = symbol
            tick.gatewayName = self.gatewayName
            self.tickDict[symbol] = tick
        else:
            tick = self.tickDict[symbol]

        tick.highPrice = float(ticker['high'])
        tick.lowPrice = float(ticker['low'])
        tick.lastPrice = float(ticker['last'])
        tick.volume = float(ticker['vol'])
        tick.date, tick.time = generateDateTime()

        newtick = copy(tick)
        self.gateway.onTick(newtick)

    # ----------------------------------------------------------------------
    # def getDepthInfo(self,symbol):
    #     """查询行情数据"""
    #     paramsDict = {"ticker_depth": 'depth', "symbol": symbol}
    #     self.sendRequest(paramsDict, self.onDepth, API_FLAG_TICKER)
    # ----------------------------------------------------------------------

    def onDepth(self, data):
        """"""
        if 'asks' not in data:
            return

        symbol = channelSymbolMap[data['symbol']]

        if symbol not in self.tickDict:
            tick = VtTickData()
            tick.symbol = symbol
            tick.vtSymbol = symbol
            tick.gatewayName = self.gatewayName
            self.tickDict[symbol] = tick
        else:
            tick = self.tickDict[symbol]

        tick.bidPrice1, tick.bidVolume1 = data['bids'][0]
        tick.bidPrice2, tick.bidVolume2 = data['bids'][1]
        tick.bidPrice3, tick.bidVolume3 = data['bids'][2]
        tick.bidPrice4, tick.bidVolume4 = data['bids'][3]
        tick.bidPrice5, tick.bidVolume5 = data['bids'][4]

        tick.askPrice1, tick.askVolume1 = data['asks'][0]
        tick.askPrice2, tick.askVolume2 = data['asks'][1]
        tick.askPrice3, tick.askVolume3 = data['asks'][2]
        tick.askPrice4, tick.askVolume4 = data['asks'][3]
        tick.askPrice5, tick.askVolume5 = data['asks'][4]

        #newtick = copy(tick)
        #self.gateway.onTick(newtick)

    # ----------------------------------------------------------------------
    def getOrders(self):
        """查询正在进行的委托订单"""
        timestamp = long(time.time())
        paramsDict = {"access_key": self.apiKey, "secret_key": self.secretKey,
                      "created": timestamp, "coin_type": 1, "method": 'get_orders'}
        sign = signature(paramsDict)
        del paramsDict["secret_key"]
        paramsDict['sign'] = sign
        self.sendRequest(paramsDict, self.onGetOrders)

    # ----------------------------------------------------------------------
    def onGetOrders(self, data):
        """回调函数"""
        if len(data) == 0:
            return
        for d in data:
            order = VtOrderData()
            order.gatewayName = self.gatewayName

            order.symbol = BTC_CNY_SPOT
            order.exchange = EXCHANGE_HUOBI
            order.vtSymbol = '.'.join([order.symbol, order.exchange])
            order.orderID = str(d['id'])
            # order.direction = directionMapReverse.get(d['side'], DIRECTION_UNKNOWN)
            order.offset = orderTypeMap[str(d['type'])]
            #order.status = orderStatusMap[str(d['status'])]

            order.price = d['order_price']
            order.totalVolume = d['order_amount']
            order.tradeVolume = d['processed_amount']
            order.orderTime = generateDateTimeStamp(d['order_time'])

            order.vtOrderID = '.'.join([self.gatewayName, order.orderID])

            self.gateway.onOrder(order)

            self.orderDict[order.orderID] = order

        #self.writeLog(u'委托信息查询完成')
    # ----------------------------------------------------------------------
    def getTrades(self):
        """查询最近的成交订单"""
        timestamp = long(time.time())
        paramsDict = {"access_key": self.apiKey, "secret_key": self.secretKey,
                      "created": timestamp, "coin_type": 1, "method": 'get_new_deal_orders'}
        sign = signature(paramsDict)
        del paramsDict["secret_key"]
        paramsDict['sign'] = sign
        self.sendRequest(paramsDict, self.onGetTrade)

    #----------------------------------------------------------------------
    def onGetTrade(self, data):
        """回调函数"""
        if len(data)==0:
            return
        for d in data:
            trade = VtTradeData()
            trade.gatewayName = self.gatewayName

            trade.symbol = BTC_CNY_SPOT
            trade.exchange = EXCHANGE_HUOBI
            trade.vtSymbol = '.'.join([trade.symbol, trade.exchange])
            trade.orderID = str(d['id'])

            #order.direction = directionMapReverse.get(d['side'], DIRECTION_UNKNOWN)
            trade.offset = tradeTypeMap[str(d['type'])]
            #order.status = orderStatusMap[str(d['status'])]

            trade.price = d['order_price']
            #order.volume = d['order_amount']
            trade.orderTime = generateDateTimeStamp(d['order_time'])

            trade.vtOrderID = '.'.join([self.gatewayName, trade.orderID])

            self.gateway.onTrade(trade)

            self.orderDict[trade.orderID] = trade

        self.writeLog(u'成交信息查询完成')

    # ----------------------------------------------------------------------
    def spotUserInfo(self):
        """查询现货账户"""
        timestamp = long(time.time())
        paramsDict = {"access_key": self.apiKey, "secret_key": self.secretKey,
                  "created": timestamp, "method": 'get_account_info'}
        sign = signature(paramsDict)
        del paramsDict["secret_key"]
        paramsDict['sign'] = sign
        self.sendRequest(paramsDict, self.onSpotUserInfo)

    # ----------------------------------------------------------------------
    def onSpotUserInfo(self, data):
        """回调函数"""
        # 持仓信息
        for symbol in ['btc', 'cny']:
                pos = VtPositionData()
                pos.gatewayName = self.gatewayName

                pos.symbol = symbol
                pos.vtSymbol = symbol
                pos.vtPositionName = symbol
                pos.direction = DIRECTION_NET

                pos.frozen = float(data['frozen_%s_display' %symbol])
                pos.position = float(data['available_%s_display' %symbol])

                self.gateway.onPosition(pos)

        account = VtAccountData()

        account.gatewayName = self.gatewayName
        account.accountID = self.gatewayName
        account.vtAccountID = account.accountID
        account.balance = float(data['net_asset'])
        self.gateway.onAccount(account)

    # ----------------------------------------------------------------------

    def sendOrder(self, params):
        """发送委托"""
        timestamp = long(time.time())
        if params.symbol == BTC_CNY_SPOT:
            coin_type=1
        else:
            coin_type=2
        if params.direction == DIRECTION_LONG:
            direction='buy'
        else:
            direction = 'sell'
        paramsDict = {"access_key": self.apiKey, "secret_key": self.secretKey,
                  "coin_type":coin_type,"price":params.price,"amount":params.volume,
                  "created": timestamp, "method": direction}
        sign=signature(paramsDict)
        del paramsDict["secret_key"]
        paramsDict['sign']=sign
        if self.trade_password:
            paramsDict["trade_password"] =self.password
        self.sendRequest(paramsDict,self.onSendOrder)

        #委托订单查询
        #self.getOrders()
        # 等待发单回调推送委托号信息
        self.orderCondition.acquire()
        self.orderCondition.wait()
        self.orderCondition.release()
        vtOrderID = '.'.join([self.gatewayName, self.lastOrderID])
        self.lastOrderID = ''
        return vtOrderID

    # ----------------------------------------------------------------------
    def onSendOrder(self,data):
        if data['result'] == 'success':
            self.lastOrderID= str(data['id'])
        # 收到委托号后，通知发送委托的线程返回委托号
        self.orderCondition.acquire()
        self.orderCondition.notify()
        self.orderCondition.release()

    # ----------------------------------------------------------------------
    def cancelOrder(self, params):
        """发送撤單"""
        timestamp = long(time.time())
        if params.symbol == BTC_CNY_SPOT:
            coin_type = 1
        else:
            coin_type = 2

        paramsDict = {"access_key": self.apiKey, "secret_key": self.secretKey,
                      "coin_type": coin_type, "id": params.orderID,"created": timestamp,
                      "method": 'cancel_order'}
        sign = signature(paramsDict)
        del paramsDict["secret_key"]
        paramsDict['sign'] = sign
        return self.sendRequest(paramsDict, self.onCancelOrder)

    # ----------------------------------------------------------------------

    def onCancelOrder(self,data):
        # if data['result'] == 'success':
        #     print "撤单完成"
        pass
    # ----------------------------------------------------------------------

    def generateUsdContract(self):
        """生成USD合约信息"""
        pass

    # ----------------------------------------------------------------------

    def onSpotTrade(self, data):
        """委托回报"""
        pass

    # ----------------------------------------------------------------------

    def onSpotCancelOrder(self, data):
        """撤单回报"""
        pass

    # ----------------------------------------------------------------------

    def spotSendOrder(self, req):
        """发单"""
        pass

    # ----------------------------------------------------------------------

    def spotCancel(self, req):
        """撤单"""
        pass
    # ----------------------------------------------------------------------


    def onSpotSubTrades(self, data):
        pass

    # ----------------------------------------------------------------------


    def onSpotOrderInfo(self, data):
        pass


def generateDateTime():
    """生成时间"""
    dt = datetime.now()
    time = dt.strftime("%H:%M:%S.%f")
    date = dt.strftime("%Y%m%d")
    return date, time

def generateDateTimeStamp(s):
    """生成时间"""
    dt = localtime(s)
    orderTime = time.strftime("%Y-%m-%d %H:%M:%S",dt)
    return orderTime

def signature(params):
    params = sorted(params.iteritems(), key=lambda d: d[0], reverse=False)
    message = urllib.urlencode(params)
    m = hashlib.md5()
    m.update(message)
    m.digest()
    sig = m.hexdigest()
    return sig



