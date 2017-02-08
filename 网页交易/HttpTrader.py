""" 同花顺模拟交易API
@version: 1.0
@author: U{jaysinco<mailto:jaysinco@163.com>;}
@brief: 提供基于'同花顺模拟炒股<http://moni.10jqka.com.cn/>'的股票买卖和查询接口
"""
from selenium import webdriver
import time
import urllib

class _Browser:
    """ 浏览器驱动主类
    @todo: 借助浏览器登陆以获取后续Http请求的cookie值
    @required: selenium.M | time.M | chromedriver.exe
    """
    def __init__(self):
        """ 初始化 
        """
        self.browser = None
    def open_browser(self):
        """ 启动Chrome浏览器 
        """
        self.browser = webdriver.Chrome() 
    def close_browser(self):
        """ 退出Chrome浏览器 
        """
        self.browser.quit()
    def login(self):
        """ 登陆'同花顺模拟炒股'
        """
        url = 'http://moni.10jqka.com.cn/'     
        self.browser.get(url)  # 访问登录页面
        # 写入账号
        account_field = self.browser.find_element_by_id('username')
        account_field.clear()
        account_field.send_keys('******')
        # 写入密码
        pwd_field = self.browser.find_element_by_id('password')
        pwd_field.clear()
        pwd_field.send_keys('******')
        # 点击登录
        login_btn = self.browser.find_element_by_css_selector('input.submit_img')
        login_btn.click()
        # 点击进入交易区
        while True:  # 等待[进入交易区]按钮出现
            try:
                enter_trade_btn = self.browser.find_element_by_xpath('//*[@title="进入交易区"]')
                enter_trade_btn.click()
            except:
                time.sleep(0.1)
            else:
                break
        while len(self.browser.window_handles) != 2:    # 等待新窗口加载
            time.sleep(0.1)
        # 关闭多余窗口
        self.browser.close()
        self.browser.switch_to.window(self.browser.window_handles[0])  
         
class HttpTrader:
    """ 模拟交易API主类
    @todo: 借助_Browser类获取cookie, 提供交易和查询功能
    @required: _Browser.C | urllib.M
    """
    def __init__(self):
        """ 初始化
        """
        pass                  
    def get_cookie(self):
        """ 获取cookie, 生成Http响应headers
        """
        # 使用selenuim登陆
        bt = _Browser()
        bt.open_browser()
        bt.login()
        # 获取cookie值
        cookie_str = ";".join([item["name"] + "=" + item["value"] for item in bt.browser.get_cookies()])     
        bt.close_browser()
        # 生成http响应header
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:43.0) Gecko/20100101 Firefox/43.0',
            'cookie': cookie_str,
        }  
    def  _convert_js_dict_str(self, js_str):
        """ 将javascript中的对象dict转为python对象
        """        
        null = None    # 未定义
        try:
            return eval(js_str)
        except:
            raise Exception('javascript对象转化失败: {}'.format(js_str))    
    def trade(self, trade_type, stock_code, stock_amount):
        """ 交易接口
        @param: 
            trade_type: String, 交易类型, sell卖出股票, buy买入股票
            stock_code: String, 交易股票代码
            stock_amount: String, 交易股票数量
        @return: 
            rtn_dict: Dict, {'errorcode': 0 if OK, 'errormsg': '', 'contract_num': 合同编号}
        """
        # 交易api地址
        trade_url = 'http://mncg.10jqka.com.cn/cgiwt/delegate/tradeStockSjwt/'
        # 判断股票市场
        stock_type = '沪A' if stock_code.startswith('6') else '深A'
        # 生成交易数据
        mkcode_map = {'深A': '1', '沪A': '2'}  
        gdzh_map = {'深A': '0086924544', '沪A': 'A462644667'}
        sjwttype_map = {'深A': '14', '沪A': '21'}  # 最优五档即时成交剩余撤销
        type_map = {'buy': 'cmd_wt_mairu', 'sell': 'cmd_wt_maichu'}
        trade_dict = {
            'type': type_map[trade_type],
            'mkcode': mkcode_map[stock_type],
            'gdzh': gdzh_map[stock_type],
            'stockcode': stock_code,
            'sjwttype': sjwttype_map[stock_type],
            'amount': stock_amount,            
        }
        # 发送交易数据
        trade_data = urllib.parse.urlencode(trade_dict).encode('utf-8')
        request = urllib.request.Request(trade_url, data=trade_data, headers=self.headers)
        response = urllib.request.urlopen(request)
        trade_statue_dict = self._convert_js_dict_str(response.read().decode('utf-8'))
        # 返回交易状态
        rtn_dict = {'errorcode': 0, 'errormsg': '', 'contract_num': None}
        if trade_statue_dict['errorcode'] != 0:
            rtn_dict['errorcode'] = trade_statue_dict['errorcode']
            rtn_dict['errormsg'] = trade_statue_dict['errormsg']
        else:
            rtn_dict['contract_num'] = trade_statue_dict['result']['data']['htbh']
        return rtn_dict
    def query(self):
        """ 查询接口, 获取当前资金状况和持仓
        @return: 
          rtn_dict: Dict, { 
             'errorcode': 0 if OK, 
             'errormsg': '', 
             'data': {
                '资金': {'可用余额','资金余额','冻结余额','总资产'}, 
                '持仓':{'证券代码,'证券名称','证券余额','可用余额','成本价'}
                }
            }
        """        
        # 查询api地址
        query_url = 'http://mncg.10jqka.com.cn/cgiwt/delegate/updateclass'
        # 获取查询数据
        query_dict = {
            'type': 'cmd_zijin_query',
            'updateClass': 'qryzijin|qryChicang|',
        }
        query_data = urllib.parse.urlencode(query_dict).encode('utf-8')
        request = urllib.request.Request(query_url, data=query_data, headers=self.headers)
        response = urllib.request.urlopen(request)
        # 返回数据定义
        rtn_dict = {'errorcode': 0, 'errormsg': '', 'data': {}}
        # 检查数据
        query_data_dict = self._convert_js_dict_str(response.read().decode('utf-8'))
        if query_data_dict['errorcode'] != 0:   
            rtn_dict['errorcode'] = query_data_dict['errorcode']
            rtn_dict['errormsg'] = query_data_dict['errormsg']
            return rtn_dict
        else:    
            qry_zijin = query_data_dict['result']['qryzijin']
            qry_chicang = query_data_dict['result']['qryChicang']
            if qry_zijin['errorcode'] != 0:
                rtn_dict['errorcode'] = qry_zijin['errorcode']
                rtn_dict['errormsg'] = qry_zijin['errormsg'] 
                return rtn_dict
            if qry_chicang['errorcode'] != 0:
                rtn_dict['errorcode'] = qry_chicang['errorcode']
                rtn_dict['errormsg'] = qry_chicang['errormsg']                  
                return rtn_dict
        # 资金信息    
        rtn_dict['data']['资金'] = {}
        rtn_dict['data']['资金']['可用余额'] = eval(qry_zijin['result']['data']['kyje'])
        rtn_dict['data']['资金']['资金余额'] = eval(qry_zijin['result']['data']['zjye'])
        rtn_dict['data']['资金']['冻结余额'] = eval(qry_zijin['result']['data']['djje'])
        rtn_dict['data']['资金']['总资产'] = eval(qry_zijin['result']['data']['zzc'])
        # 持仓信息
        rtn_dict['data']['持仓'] = []
        for stock_hold in qry_chicang['result']['list']:
            stock_info = {}
            stock_info['证券代码'] = stock_hold['d_2102']
            stock_info['证券名称'] = stock_hold['d_2103']
            stock_info['证券余额'] = eval(stock_hold['d_2117'])
            stock_info['可用余额'] = eval(stock_hold['d_2121'])
            stock_info['成本价'] = eval(stock_hold['d_2122'])
            rtn_dict['data']['持仓'].append(stock_info)
        # 返回数据
        return rtn_dict
    def sprint_account_statue(self, query_rtn=None):
        """ 输出账号状况(资金、持仓)字符串
        @param:
            query_rtn: Dict, 没有则查询，否则用传入的数据
        @return:
            account_str: String, 账号状态字符串
        """        
        query_rtn = query_rtn if query_rtn else self.query()
        account_str = ''
        if query_rtn['errorcode'] != 0:
            return account_str
        # 输出格式
        chicang = query_rtn['data']['持仓']
        zijin = query_rtn['data']['资金']
        zzc, kyye, djzj = zijin['总资产'], zijin['可用余额'], zijin['冻结余额']
        mtitle_str = "{0:>12}|{1:>12}|{2:>12}|".format('Total', 'Usable', 'Frozen')
        m_str = "{0:>12}|{1:>12}|{2:>12}|".format(zzc, kyye, djzj)
        xia_hua = ' '*4+'-'*35
        money_str = "{}\n{}\n{}\n".format(mtitle_str, xia_hua, m_str)
        
        
    def check_http_statue(self):
        """ 检查http连接是否异常
        """
        rtn_dict = {'errorcode': 0, 'errormsg': '网络连接正常'}
        try:
            urllib.request.urlopen('http://www.baidu.com')
        except:
            rtn_dict['errorcode'] = 99    
            rtn_dict['errormsg'] = '网络连接中断'
            return rtn_dict
        else:
            return rtn_dict


