import time
import os
import sys
import datetime
import QuantityTradeTools as qtt
import pickle


class 小盘股策略:
    '''
    条件一：前22日的平均收盘价≤12; 
    条件二：流通盘≤5亿;
    条件三：当前成交量>MA*增大倍数
    满足条件一和条件二，计算指标值=流通盘*昨日收盘价；对当日所有有交易的股票指标值从小到大排名   
    买入前五十支股票中满足条件三的股票。
    第二天重新排名后，把掉到五十名之后的股票卖掉，买入重新进入前五十名的股票。盘中动态选股，每次选择一支股票进行平仓。
    若能选择到股票平仓或若持股数小于最大持股数，则选择一支股票开仓。
    '''
    def __init__(self):
        self.日志 = qtt.Logger()
        self.交易 = qtt.Trader('交易系统.exe', reSetSelfWindow=False)
        self.行情 = qtt.Market()
        self.today = datetime.date.today().strftime('%Y-%m-%d')
        # 载入今日交易数据
        dataPath = '.\Trade_data.pkl'
        fp = open(dataPath, 'rb')
        tradeData = pickle.load(fp)
        fp.close()
        self.tradeDay = tradeData['trade_day'][self.today[:4]]   # 本年的交易日
        self.rankStock = tradeData['rank_stock']         # 今日参与排名的股票代码
        self.日志.log('本次参与排名的股票有{}个'.format(len(self.rankStock)))
        # 判断交易日   
        if self.today in self.tradeDay:   # 判断数据文件基准日期是否为当前交易日的前一交易日                
            shouldBe = self.tradeDay[self.tradeDay.index(self.today)-1]
            if tradeData['gen_day'] != shouldBe:
                self.日志.log('数据文件{}基准日期错误, 应为{}!!'.format(dataPath, shouldBe))
                os.system('pause')
                sys.exit(0)
        else:
            self.日志.log('今天不是交易日, 下一交易日为{}!!'.format(self.nextTradeDay()))
            os.system('pause')
            sys.exit(0)
        # 策略参数      
        self.可买股票上限 = 50
        self.选股数量 = 30
        self.委托单停留时间 = 15  # 秒
        self.仓位 = 0.5    
        self.成交量增大倍数 =  0 #1.5
        self.策略开始时间 = self.行情.fixDateTime(10,0)
        self.策略结束时间 = self.行情.fixDateTime(14,55)
        self.日志.log('[仓位] {} | [持仓Max] {} | [交易时间] {} ~ {}'.format(self.仓位, self.可买股票上限, self.策略开始时间.strftime('%H:%M'), self.策略结束时间.strftime('%H:%M')))
        self.日志.log('系统初始化完毕!')
    
    def nextTradeDay(self): 
        if self.today in self.tradeDay:
            return self.tradeDay[self.tradeDay.index(self.today)+1]
        else:
            for td in self.tradeDay:
                if td > self.today:
                    break
            return td
    
    def calBuyAmount(self, 资金Struct, 价格):
        ''' 计算每股购买数量'''
        每股买入金额 = 资金Struct.总资产*self.仓位/(self.可买股票上限)
        return round(每股买入金额/价格/100)*100              
            
    def genSuggestList(self):
        ''' 根据目前行情指标和目前持仓，生成推荐买入和卖出的清单'''  
        持仓列表 = self.交易.查询持仓()  
        持仓codeList = [持仓Struct.代码 for 持仓Struct in 持仓列表]
        rankList = list(self.rankStock.keys())
        nowDict = self.行情.getStkListNowQuotes(rankList)
        indexTuple = [(stkCode,nowDict[stkCode]['price']*self.rankStock[stkCode]['nonrestfloatA']) for stkCode in rankList]
        topTuple = sorted(indexTuple, key=lambda dd: dd[1])[self.选股数量*(-1):]
        # 生成推荐买入清单
        buyList = []
        topList = []
        for tup in topTuple:
            code = tup[0]
            topList.append(code)
            if nowDict[code]['vol'] >= self.成交量增大倍数*self.rankStock[code]['vol_MA'] \
                and (code not in 持仓codeList):
                buyList.append(code)     # 此时指标最大的在列表最后
        # 生成推荐卖出清单
        sellList = [持仓Struct for 持仓Struct in 持仓列表 if ((持仓Struct.代码 not in topList) and (持仓Struct.可用余额>0))]
        return len(持仓列表), buyList, sellList       
        
    def 委托单全撤(self):       
        self.日志.log('[全撤] 撤销全部委托单!')
        可撤订单列表 = self.交易.查询可撤订单()
        if len(可撤订单列表) != 0:
            if len(可撤订单列表) == 1:
                self.交易.撤单(可撤订单列表[0])  
            elif len(可撤订单列表)>1:
                self.交易.撤单()  
            while(len(self.交易.查询可撤订单()) != 0):
                time.sleep(0.5)                

    def 持仓全卖(self):
        self.日志.log('[全卖] 卖出全部可卖的持仓!')
        持仓列表 = self.交易.查询持仓()     
        for 持仓Struct in 持仓列表:
            if  持仓Struct.可用余额 > 0:
                price = self.行情.getStkSingleNowPrice(持仓Struct.代码, 'bid')
                if price != 0:
                    self.交易.买卖(持仓Struct.代码, price, 持仓Struct.可用余额, '卖出')             
        
    def tick(self):
        ''' 每个循环执行一次执行 '''
        目前持仓个数,buyList, sellList = self.genSuggestList()      
        self.日志.log('[行情] 目前持仓{}, 推荐买入{}, 推荐卖出{}'.format(目前持仓个数,len(buyList), len(sellList)))
        #**************************** 买入股票 *******************************************  
        # 查资金
        资金Struct = self.交易.查询资金() 
        # 当前持仓<可买股票上限
        while len(buyList) > 0 and 目前持仓个数 < self.可买股票上限:
            目前排名最高 = buyList.pop()    
            nowPrice = self.行情.getStkSingleNowPrice(目前排名最高, 'price')
            if nowPrice != 0:
                amount = self.calBuyAmount(资金Struct, nowPrice)
                price = self.行情.getStkSingleNowPrice(目前排名最高, 'ask')
                if price != 0:
                    self.交易.买卖(目前排名最高, price, amount, '买入')  
                    self.日志.log('[买入] 以{}元/股买入{}股{}'.format(price,amount,目前排名最高))   
                    目前持仓个数 += 1
                else:
                    self.日志.log('[买入] {}不可交易!!'.format(目前排名最高))
        #**************************** 卖出股票 *******************************************                                   
        # 卖出持仓中今日可卖 && 不在排名榜上的股票
        for 持仓Struct in sellList:
            price = self.行情.getStkSingleNowPrice(持仓Struct.代码, 'bid')
            if price != 0:
                self.交易.买卖(持仓Struct.代码, price, 持仓Struct.可用余额, '卖出')
                单笔盈亏 = round((price - 持仓Struct.成本价)/持仓Struct.成本价*100,1)
                self.日志.log('[卖出] 以{}元/股卖出{}股{}, 单笔盈亏{}%.'.format(price,持仓Struct.可用余额,持仓Struct.代码,单笔盈亏)) 
            else:
                self.日志.log('[卖出] {}不可交易!!'.format(持仓Struct.代码))
        # 等待委托成交                   
        time.sleep(self.委托单停留时间)                    
        self.委托单全撤()    # 委托全撤  
        
    def run(self):           
        # 开始一天的交易
        while True:               
            nowFlag = self.行情.isNowInTradeTime()
            if nowFlag == 1:
                self.日志.log('早晨还未开盘，等待开盘...')
                self.行情.waitForSomeSeconds((self.行情.早开 - datetime.datetime.now()).seconds)
                time.sleep(0.5)
                self.日志.log('早上开盘!')
            elif nowFlag == 3:
                self.日志.log('中午休息，等待开盘...')
                self.行情.waitForSomeSeconds((self.行情.下始 - datetime.datetime.now()).seconds)
                time.sleep(0.5)
                self.日志.log('下午开盘!')
            elif nowFlag == 5:
                self.日志.log('股票交易已经闭市!!')
                return
            else:
                now = datetime.datetime.now()
                if now >= self.策略开始时间 and now <= self.策略结束时间:
                    self.tick()
                elif now < self.策略开始时间:
                    self.日志.log('还未到策略交易时间, 等待...')
                    self.行情.waitForSomeSeconds((self.策略开始时间 - datetime.datetime.now()).seconds)
                    time.sleep(0.5)
                    self.日志.log('策略开始交易!')
                else:
                    self.日志.log('策略已经结束交易!!')
                    return
                
        
straG = 小盘股策略()
straG.run() 
#straG.tick()
#straG.持仓全卖()
#straG.委托单全撤()

os.system('pause')























