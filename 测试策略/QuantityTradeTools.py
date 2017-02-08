import sys
import time
import mmap
import copy
import ctypes  
import datetime
import dateutil.parser 
import struct
import win32gui
import win32con
import win32event 
import tushare as ts 
import http.client
import urllib.request

#************************************** 行情策略系统 ************************************
      
# 行情类
class Market:
    def __init__(self): 
        pass
            
    def fixDateTime(self, hour, minute): 
        today = datetime.date.today()
        return datetime.datetime(today.year,today.month,today.day,hour,minute)

    # 现在是否处于交易时间
    def isNowInTradeTime(self):    # 1 早上未开盘  2 早盘  3 中午休息   4 下午盘   5 结盘   
        # 交易特殊时刻
        self.早开 = self.fixDateTime(9,30)
        self.午休 = self.fixDateTime(11,30)
        self.下始 = self.fixDateTime(13,0)
        self.结束 = self.fixDateTime(15,0) 
        # 判断
        now = datetime.datetime.now()
        if now < self.早开:  return 1 
        elif now >= self.早开 and now <= self.午休:  return 2 
        elif now > self.午休 and now < self.下始:  return 3   
        elif now >= self.下始 and now <= self.结束:  return 4
        elif now > self.结束:  return 5   

    # 等待
    def waitForSomeSeconds(self, sec):
        now = datetime.datetime.now() 
        minGapSec = 60
        if 0 < sec <= minGapSec:
            time.sleep(sec)
            return 
        elif sec > minGapSec:
            gap = datetime.timedelta(seconds=sec)
            target = now + gap
            round = sec//minGapSec - 1
            for i in range(round):
                time.sleep(minGapSec)
            now = datetime.datetime.now()
            stillGap = (target - now).seconds + 1
            time.sleep(stillGap)
            return        
                          
#********************** Tushare API 自定义的应用 *************************************  
    def tsDayTypePreProcess(self, day):
        ''' Tushare日期必须是YYYY-MM-DD, 此函数处理day参数'''   
        if type(day) == str:
            return dateutil.parser.parse(day).date().strftime('%Y-%m-%d')
        elif type(day) == datetime.date:
            return day.strftime('%Y-%m-%d')
        else:
            raise RuntimeError('day参数类型错误!')             
        
    def getStkListNowQuotes(self, stockList):
        ''' 批量获取当前行情 '''
        atOneTime = 30  # 一次性获取的股票现价个数
        nowDict = {}
        while len(stockList) > atOneTime:
            thisTime = stockList[:atOneTime]
            stockList = stockList[atOneTime:]
            data = ts.get_realtime_quotes(thisTime)
            nowPrice = data['price'].values
            nowVolume = data['volume'].values
            for index,code in enumerate(thisTime):
                nowDict[code] = {'price':eval(nowPrice[index]), 'vol':eval(nowVolume[index])}
        # 最后剩下的
        if len(stockList)>0:
            data = ts.get_realtime_quotes(stockList)
            nowPrice = data['price'].values
            nowVolume = data['volume'].values
            for index,code in enumerate(stockList):
                nowDict[code] = {'price':eval(nowPrice[index]), 'vol':eval(nowVolume[index])}
        return nowDict
        
    def getStkSingleNowPrice(self, code, flag): # -> float   flag: 'ask' 卖一价;'bid' 买一价;'price'  现价   
        ''' 获取单个股票当前价格，卖/买一价 '''        
        price = ts.get_realtime_quotes(code).T[0][flag]    
        return round(float(price),2)

      
# 通联数据来源
class WMCloudClient:
    domain = 'api.wmcloud.com'
    port = 443
    token = ''
    httpClient = None
    def __init__(self, token):
        self.token = token
        self.httpClient = http.client.HTTPSConnection(self.domain, self.port)
        
    def __del__(self):
        if self.httpClient is not None:
            self.httpClient.close()
            
    def encodepath(self, path):
        #转换参数的编码
        start=0
        n=len(path)
        re=''
        i=path.find('=',start)
        while i!=-1 :
            re+=path[start:i+1]
            start=i+1
            i=path.find('&',start)
            if(i>=0):
                for j in range(start,i):
                    if(path[j]>'~'):
                        re+=urllib.request.quote(path[j])
                    else:
                        re+=path[j]  
                re+='&'
                start=i+1
            else:
                for j in range(start,n):
                    if(path[j]>'~'):
                        re+=urllib.quote(path[j])
                    else:
                        re+=path[j]  
                start=n
            i=path.find('=',start)
        return re
        
    def getData(self, path):
        result = None
        path='/data/v1'+path
        path=self.encodepath(path)      
        self.httpClient.request('GET', path, headers = {"Authorization": "Bearer " + self.token})
        response = self.httpClient.getresponse()
        # 真奇怪，编码居然是gbk
        result = response.read().decode('gbk')
        # 正常则返回 status == 200
        if response.status == 200:
            return result
        else:
            raise RuntimeError('通联数据连接失败!')

#********************** 通联数据 API 自定义的应用 *************************************  
    def wmDayTypePreProcess(self, day):   
        ''' 通联数据日期必须是YYYYMMDD, 此函数处理day参数'''   
        if type(day) == str:
            return dateutil.parser.parse(day).date().strftime('%Y%m%d')
        elif type(day) == datetime.date:
            return day.strftime('%Y%m%d')
        else:
            raise RuntimeError('day参数类型错误!') 
            
    # 自动参数赋值
    def parseDataList(self, data, field, keyInField):
        dataList = data.split('\n')[1:-1]
        keyIndex = field.index(keyInField)
        resDict = {}
        for line in dataList:
            paramTuple = line.split(',')
            key = eval(paramTuple[keyIndex])
            resDict[key] = {}
            for index,param in enumerate(field):
                if param == keyInField:
                    continue
                rawStr = paramTuple[index] if paramTuple[index]!='' else 'None'
                resDict[key][param] = eval(rawStr)
        return resDict            
 
        
#************************************** 存储系统 ************************************
            
# 日志类
class Logger:
    def __init__(self):    
        pass    
            
    def log(self, msg, color=0x07, end='\n'):
        '''
            命令行带颜色输出，立即模式，没有换行，颜色模式如下：
            FOREGROUND_BLACK = 0x00 # black.
            FOREGROUND_DARKBLUE = 0x01 # dark blue.
            FOREGROUND_DARKGREEN = 0x02 # dark green.
            FOREGROUND_DARKSKYBLUE = 0x03 # dark skyblue.
            FOREGROUND_DARKRED = 0x04 # dark red.
            FOREGROUND_DARKPINK = 0x05 # dark pink.
            FOREGROUND_DARKYELLOW = 0x06 # dark yellow.
            FOREGROUND_DARKWHITE = 0x07 # dark white.
            FOREGROUND_DARKGRAY = 0x08 # dark gray.
            FOREGROUND_BLUE = 0x09 # blue.
            FOREGROUND_GREEN = 0x0a # green.
            FOREGROUND_SKYBLUE = 0x0b # skyblue.
            FOREGROUND_RED = 0x0c # red.
            FOREGROUND_PINK = 0x0d # pink.
            FOREGROUND_YELLOW = 0x0e # yellow.
            FOREGROUND_WHITE = 0x0f # white.
        '''
        #STD_INPUT_HANDLE = -10
        #STD_ERROR_HANDLE = -12
        STD_OUTPUT_HANDLE = -11
        # 写入前缀
        timeStr = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())
        sys.stdout.write(timeStr+' <>  ')
        sys.stdout.flush()
        # 获取标准输出句柄  
        handle = ctypes.windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        # 设定颜色
        ctypes.windll.kernel32.SetConsoleTextAttribute(handle, color)
        # 立即写入,不缓冲
        sys.stdout.write(msg+end)
        sys.stdout.flush()
        # 还原
        ctypes.windll.kernel32.SetConsoleTextAttribute(handle, 0x07)
    
        
#************************************** 交易系统 ************************************

# 命令映射类
class CmdFileMap:
    def __init__(self, tagName='trader_msg', size = 1024*1024):
        self.fm = mmap.mmap(-1, size, access=mmap.ACCESS_WRITE, tagname=tagName)
        self.eventAu = win32event.OpenEvent(win32event.EVENT_ALL_ACCESS, 0 ,"aauto_trigger")
        self.eventPy = win32event.OpenEvent(win32event.EVENT_ALL_ACCESS, 0 ,"python_trigger")
        self.timeOut = 0xFFFFFFFF  #无穷等待
        win32event.ResetEvent(self.eventAu)
        win32event.ResetEvent(self.eventPy)
    
    def sendCmd(self, cmd_id, arg=None): 
        self.fm.seek(0) 
        # 写入命令号    
        cmd = struct.pack('i', cmd_id)        
        self.fm.write(cmd) 
        # 发送一个struct字节码
        if arg:
            self.fm.write(arg)
        # 触发AAuto信号
        win32event.ResetEvent(self.eventPy)
        win32event.SetEvent(self.eventAu)
        
    def getSingleStructReply(self, struct_instance):  
        self.fm.seek(0)
        # 获取单结构体回报          
        if win32event.WaitForSingleObject(self.eventPy, self.timeOut) == 0:
            struct_instance.readFromFileMap(self.fm)
            return struct_instance

    def getMultiStructReply(self, struct_instance):
        self.fm.seek(0)
        instance_list = []
        # 获取结构体数量       
        if win32event.WaitForSingleObject(self.eventPy, self.timeOut) == 0:
            instance_num, = struct.unpack('i', self.fm.read(4))          
            for i in range(instance_num):
                struct_instance.readFromFileMap(self.fm)
                instance_list.append(copy.copy(struct_instance))
            return instance_list 
 

# 数据类型
# 各类型的字节数到快手中..raw.sizeof测一下就行啦 
class 状态:
    def __init__(self):
        self.isOK = ""
        self.msg = ""
    
    def readFromFileMap(self, pFileMap):
        self.isOK, self.msg = struct.unpack('i50s', pFileMap.read(54))
        self.msg  = self.msg.decode('gbk').strip('\x00')
 
 
class 资金:
    def __init__(self):
        self.可用 = 0.0
        self.总资产 = 0.0
        
    def readFromFileMap(self, pFileMap):
        self.可用, self.总资产 = struct.unpack('2f', pFileMap.read(8))
        self.可用 = round(self.可用, 2)
        self.总资产 = round(self.总资产, 2)

class 持仓:
    def __init__(self):
        self.代码 = ""
        self.名称 = "" 
        self.可用余额 = 0 
        self.股票余额 = 0 
        self.成本价 = 0.0 
        self.市价 = 0.0
        
    def readFromFileMap(self, pFileMap):
        self.代码, self.名称, self.可用余额, self.股票余额, self.成本价, self.市价 = struct.unpack(
                    '6s30s2i2f', pFileMap.read(52))
        self.代码 = self.代码.decode('gbk').strip('\x00')
        self.名称 = self.名称.decode('gbk').strip('\x00')
 
 
class 订单:
    def __init__(self, 代码="", 价格=0.0, 数量=0, 方向=""):
        self.代码= 代码
        self.价格 = 价格
        self.数量 = 数量
        self.方向 = 方向
        self.名称 = ""
        self.备注 = ""
        self.时间 = ""
        self.日期 = ""
        self.合同编号 = "all"
        
    def toBinary(self):
        return struct.pack('6sif4s30s30s8s8s12s', 
            self.代码.encode('gbk'), self.数量, self.价格, self.方向.encode('gbk'),
            self.名称.encode('gbk'), self.备注.encode('gbk'), self.时间.encode('gbk'), 
            self.日期.encode('gbk'), self.合同编号.encode('gbk')) 
    
    def readFromFileMap(self, pFileMap):
        self.代码, self.数量, self.价格, self.方向, self.名称, self.备注, self.时间, self.日期, self.合同编号 = struct.unpack(
                    "6sif4s30s30s8s8s12s", pFileMap.read(108))
        self.代码 = self.代码.decode('gbk').strip('\x00')
        self.方向 = self.方向.decode('gbk').strip('\x00')
        self.备注 = self.备注.decode('gbk').strip('\x00')
        self.名称 = self.名称.decode('gbk').strip('\x00')
        self.合同编号 = self.合同编号.decode('gbk').strip('\x00')
        self.时间 = self.时间.decode('gbk').strip('\x00')
        self.日期 = self.日期.decode('gbk').strip('\x00')
        
 
# 和交易系统的接口类  
class Trader:
    def __init__(self, 交易系统Name, reSetSelfWindow=False):
        # 设置本程序窗口位置
        if reSetSelfWindow:
            本程序hwnd = win32gui.FindWindow("ConsoleWindowClass", r"D:\ProgramFiles\Anaconda3\python.exe")
            win32gui.SetWindowPos(本程序hwnd, win32con.HWND_TOP, 0,370,800,350, win32con.SWP_SHOWWINDOW) 
        # 设置交易系统窗口位置
        self.交易系统hwnd = win32gui.FindWindow("ConsoleWindowClass", 交易系统Name)
        if not self.交易系统hwnd:
            raise RuntimeError('外部程序"{}"未开启!'.format(交易系统Name))
        win32gui.SetWindowPos(self.交易系统hwnd, win32con.HWND_TOP, 0,0,800,350, win32con.SWP_SHOWWINDOW) 
        # 命令文件映射
        self.cmdFM = CmdFileMap()
             
    def 查询资金(self):
        self.cmdFM.sendCmd(201)
        money = self.cmdFM.getSingleStructReply(资金())
        return money
        
    def 查询持仓(self):
        self.cmdFM.sendCmd(202)
        stockHave_list = self.cmdFM.getMultiStructReply(持仓())
        return stockHave_list
        
    def 查询可撤订单(self):
        self.cmdFM.sendCmd(203)
        order_list = self.cmdFM.getMultiStructReply(订单())
        return order_list
        
    def 买卖(self, 代码, 价格, 数量, 方向):
        self.cmdFM.sendCmd(301, 订单(代码, 价格, 数量, 方向).toBinary())   
        statue = self.cmdFM.getSingleStructReply(状态())             
        return statue
    
    def 撤单(self, order_instance=订单()):   # 默认的订单().合同编号=='all', 即订单全撤
        self.cmdFM.sendCmd(302, order_instance.toBinary())
        statue = self.cmdFM.getSingleStructReply(状态())
        return statue

    