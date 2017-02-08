import QuantityTradeTools as qtt
import os
import pickle
import sys


class GenTradeData:
    def __init__(self):
        self.dataPath = 'Trade_data.pkl'
        self.wmclient = qtt.WMCloudClient('379efb8766ed8bd5c822e94b2ea1e91b8129b819760a8e58eefaa0296a0f8db7')
        self.日志 = qtt.Logger()    
    
    def dumpToFile(self, obj):
        fp = open(self.dataPath, 'wb')
        pickle.dump(obj, fp)
        fp.close()  
               
    def wm_getTradeCal(self, startDay, endDay): 
        ''' 获取一段时间的交易所日历：是否开放交易 '''
        startDay = self.wmclient.wmDayTypePreProcess(startDay)
        endDay = self.wmclient.wmDayTypePreProcess(endDay)
        url = '/api/master/getTradeCal.csv?field={0}&exchangeCD=XSHG&beginDate={1}&endDate={2}'
        field = ['calendarDate','isOpen']
        data = self.wmclient.getData(url.format(",".join(field), startDay, endDay))
        return self.wmclient.parseDataList(data, field, 'calendarDate')

    def wm_getEqu(self):
        ''' 获取A股基本信息：上市状态、流通股数量 '''
        url = '/api/equity/getEqu.csv?field={0}&listStatusCD=L&secID=&ticker=&equTypeCD=A'
        field = ['ticker','listStatusCD','nonrestfloatA']        
        data = self.wmclient.getData(url.format(",".join(field))) 
        return self.wmclient.parseDataList(data, field, 'ticker') 
 
    def wm_getStockFactorsOneDay(self, day):
        ''' 获取股票因子数据：MA20 '''
        day = self.wmclient.wmDayTypePreProcess(day)
        url = '/api/market/getStockFactorsOneDay.csv?field={0}&secID=&ticker=&tradeDate={1}'
        field = ['ticker','MA20']                 
        data = self.wmclient.getData(url.format(",".join(field),day))         
        return self.wmclient.parseDataList(data, field, 'ticker') 
        
    def wm_getMktEqud(self, code, startDay, endDay):
        ''' 获取某股票某一段时间日线信息：成交量 '''
        startDay = self.wmclient.wmDayTypePreProcess(startDay)
        endDay = self.wmclient.wmDayTypePreProcess(endDay)
        url = '/api/market/getMktEqud.csv?field={0}&beginDate={1}&endDate={2}&secID=&ticker={3}&tradeDate='
        field = ['tradeDate', 'turnoverVol']         
        data = self.wmclient.getData(url.format(",".join(field),startDay,endDay,code))      
        return self.wmclient.parseDataList(data, field, 'tradeDate')
        
    def genYearTradeDay(self, year):
        rtn = []
        yearStart = '{}0101'.format(year)
        yearEnd = '{}1230'.format(year)
        dataDict = self.wm_getTradeCal(yearStart, yearEnd)
        for date in sorted(dataDict.keys()):
            if dataDict[date]['isOpen'] == 1:
                rtn.append(date)
        return rtn
    
    def genRankStkVolumeRate(self, rtnDict, dataDay):
        '''
        步骤一：前20日的平均收盘价≤12; 
        步骤二：流通盘≤5亿;
        步骤三：生成N日平均成交量
        '''
        rtn = {}
        # 判断所给日期是否是成交日
        今年交易日 = rtnDict['trade_day'][dataDay[:4]]
        assert(type(dataDay) == str and len(dataDay) == 10 and dataDay in 今年交易日)        
        # 生成备选股票
        stkBscInfo = self.wm_getEqu()
        stkFactors = self.wm_getStockFactorsOneDay(dataDay)
        rankStandard = lambda stkCode: stkBscInfo[stkCode]['listStatusCD']=='L' and stkBscInfo[stkCode]['nonrestfloatA']<=5e8 \
                              and (stkCode in stkFactors.keys()) and stkFactors[stkCode]['MA20']!=None and stkFactors[stkCode]['MA20']<=12
        rankList = [stkCode for stkCode in stkBscInfo.keys() if rankStandard(stkCode)]
        # 生成成交量均线
        NDay = 5   # 成交量均线长度
        NDaysAgo = 今年交易日[今年交易日.index(dataDay)-NDay+1]
        self.日志.log('  - 股票池容量: 0000',end='')
        个数 = 0
        for stkCode in rankList:
            try:
                dataDict = self.wm_getMktEqud(stkCode, NDaysAgo, dataDay)
            except: continue
            volumeList = [dic['turnoverVol'] for dic in dataDict.values()]
            if (0 in volumeList or len(volumeList) != NDay): continue  # 过去N个交易日有停牌的股票不加入备选股票中
            rtn[stkCode] = {'vol_MA':sum(volumeList)/len(volumeList), 'nonrestfloatA':stkBscInfo[stkCode]['nonrestfloatA']}
            个数 += 1
            sys.stdout.write('\b\b\b\b{0:>04d}'.format(个数))
            sys.stdout.flush()
        sys.stdout.write('\n')
        return rtn
   
        
    def run(self):
        rtnDict = {}        
        # 写入交易日
        self.日志.log('获取全年交易日...')
        rtnDict['trade_day'] = {}
        for year in ['2014', '2015']:
            self.日志.log('  - {}'.format(year))
            rtnDict['trade_day'][year] = self.genYearTradeDay(year)
        self.日志.log('DONE!!')
        
        # 写入备选股票和成交量5日均值
        self.日志.log('获取备选股票...')
        基准日 = '2015-10-15'    # 该天应该为尚未交易日的前一交易日，格式必须为'yyyymmdd'
        self.日志.log('  - 基准日: {}'.format(基准日))
        rtnDict['rank_stock'] = GTD.genRankStkVolumeRate(rtnDict, 基准日)
        self.日志.log('DONE!!')
        
        # 写入生成基准日
        rtnDict['gen_day'] = 基准日
        
        # 写入文件
        self.日志.log('写入pkl文件...')
        self.日志.log('  - 路径: {}'.format(self.dataPath))
        self.dumpToFile(rtnDict)
        self.日志.log('DONE!!')


    def 测试pkl文件(self):
        self.日志.log('')
        self.日志.log('')
        self.日志.log('')
        self.日志.log('********* 测试 *********')
        fp = open(self.dataPath, 'rb')
        dataDict = pickle.load(fp)
        fp.close()  
        # gen_day
        self.日志.log('★本数据制作基准日: {}'.format(dataDict['gen_day']))
        # rank_stock
        self.日志.log('')
        self.日志.log('★rank_stock: {}个子对象'.format(len(dataDict['rank_stock'])))
        self.日志.log('PEEK随机3个如下: ')
        for key in list(dataDict['rank_stock'])[:3]:
            self.日志.log("   => '{}':{}".format(key, dataDict['rank_stock'][key]))
        # trade_day    
        self.日志.log('')
        self.日志.log('★trade_day: {}个子对象'.format(len(dataDict['trade_day'])))
        for key in list(dataDict['trade_day']):
            self.日志.log("   => {}: {}个日期".format(key, len(dataDict['trade_day'][key])))
        

GTD = GenTradeData()
GTD.run()
GTD.测试pkl文件()
os.system('pause')




















