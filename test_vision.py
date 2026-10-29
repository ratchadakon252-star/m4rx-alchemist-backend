import base64,io,os,unittest
from unittest.mock import patch
from PIL import Image
from vision_api import VisionError,prepare_images,_check_plan,analyze_image_request

def png_data():
    img=Image.new('RGB',(640,350),(20,30,40))
    b=io.BytesIO();img.save(b,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()

class Tests(unittest.TestCase):
    def setUp(self):self.images={k:png_data() for k in ('H1','M15','M5')}
    def test_correct_images(self):self.assertEqual(len(prepare_images(self.images,1)),3)
    def test_missing_m5_rejected(self):
        with self.assertRaisesRegex(VisionError,'M5'):prepare_images({'H1':png_data(),'M15':png_data()},1)
    def test_corrupt_base64(self):
        images=dict(self.images);images['M15']='data:image/png;base64,___'
        with self.assertRaises(VisionError):prepare_images(images,1)
    def test_missing_provider_blocks(self):
        with patch.dict(os.environ,{'ALCHEMIST_VISION_PROVIDER':'','ALCHEMIST_VISION_API_KEY':''}):
            with self.assertRaisesRegex(VisionError,'ตั้งค่า AI Vision'): analyze_image_request({'mode':1,'images':self.images})
    def test_check_math(self):
        x={'direction':'SELL','model':'Breaker','order_type':'SELL LIMIT','trigger':'CONFIRMED',
           'entry':4004,'sl':4007,'tp1':3999,'tp2':3994,'evidence':'visible breaker',
           'stop_reason':'above sweep','target_reason':'liquidity low','timeframe':'M5'}
        res=_check_plan(x,1);self.assertTrue(res['complete']);self.assertEqual(res['rr1'],1.67)
        x['sl']=3999;self.assertFalse(_check_plan(x,1)['complete'])
        x['sl']=4007;x['trigger']='UNKNOWN';self.assertFalse(_check_plan(x,1)['complete'])
    def test_no_prices_if_axis_not_readable(self):
        fake={'images':{tf:{'readable':True,'symbol_visible':True,'price_axis_readable':tf!='M5','observations':'chart visible'} for tf in self.images},
              'bias':'SELL','narrative':'down','liquidity_path':'low',
              'setups':[{'direction':'SELL','model':'Breaker','order_type':'SELL LIMIT','trigger':'CONFIRMED',
                         'entry':4004,'sl':4007,'tp1':3999,'tp2':3994,'evidence':'visible','stop_reason':'above','target_reason':'low'}]}
        with patch('vision_api._query_ai',return_value=(fake,'mock','mock')):
            out=analyze_image_request({'mode':1,'images':self.images})
        self.assertFalse(out['setups'][0]['complete'])
        self.assertFalse(out['real_chart_validation_passed'])
        self.assertEqual(out['engine_validation'],'NOT_RUN_WITH_NATIVE_OHLC')
    def test_mode2_no_trade(self):
        fake={'images':{},'setups':[{'direction':'BUY'}],'bias':'BUY'}
        with patch('vision_api._query_ai',return_value=(fake,'mock','mock')):
            out=analyze_image_request({'mode':2,'images':self.images})
        self.assertEqual(out['setups'],[])
    def test_m1_required_for_mode5(self):
        with self.assertRaisesRegex(VisionError,'M1'):prepare_images(self.images,5)

if __name__=='__main__': unittest.main()
