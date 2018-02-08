#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bottle import route, run, request, response, hook
from datetime import datetime
import serial
import time
import json
import commands
import os
import slackweb
import traceback
import requests


ir_serial = serial.Serial("/dev/ttyACM0", 9600, timeout = 1)
IR_DATA_DIR = "/home/pi/House/irm/irjson/"
slack = slackweb.Slack(url="https://hooks.slack.com/services/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")
CRON_FILE = "/home/pi/House/irm/crontab"
LOG_FILE_DIR = "/home/pi/House/MadEYE/log/"
LOG_FILE_NAME = "irm_server"
STATE_FILE_DIR = "/home/pi/House/irm/state.json"
BIG_MOUTH = "http://192.168.1.8:10080/speak?talk="

slack.notify(text="DCLABO was done boot.")

try:
    def playIR(path):
        if path and os.path.isfile(path):
            print("Playing IR with %s ..." % path)
            f = open(path)
            data = json.load(f)
            f.close()
            recNumber = len(data['data'])
            rawX = data['data']
        
            ir_serial.write(b"n,%d\r\n" % recNumber)
            ir_serial.readline()
        
            postScale = data['postscale']
            ir_serial.write(b"k,%d\r\n" % postScale)
        #time.sleep(1.0)
            msg = ir_serial.readline()
        #print(msg)
        
            for n in range(recNumber):
                bank = n / 64
                pos = n % 64
                if (pos == 0):
                    ir_serial.write(b"b,%d\r\n" % bank)
            
                ir_serial.write(b"w,%d,%d\n\r" % (pos, rawX[n]))
        
            ir_serial.write(b"p\r\n")
            msg = ir_serial.readline()
            print(msg)
            #ir_serial.close()
        else:
            print("Playing IR...")
            ir_serial.write(b"p\r\n")
            time.sleep(1.0)
            msg = ir_serial.readline()
            print(msg)

    def search_ir_data(device):
        path = IR_DATA_DIR

        if device == "pj":
            path += "pj_on.json"
        elif device == "aircon":
            path += "aircon.json"
        elif device == "ac_up":
            path += "ac_on.json"
        elif device == "ac_dw":
            path += "ac_dw.json"
        elif device == 'li-single':
            path += 'light.json'
        elif device == 'li-double':
            path += 'light.json'
            # ここで１回実行しちゃう
            # ことでダブルショットができる。
            playIR(path)
        elif device == 'dr':
            print("Do you call me?")
            
        MadEYE(device)
        return path

    @hook('after_request')
    def enable_cors():
        response.content_type = 'application/json'

    def appliances_response_json(device, function, parameter, result):
        obj = {'device':device, 'function':function, 'parameter':parameter, 'result':result}
        return json.dumps(obj)

    @route('/myhome')
    def control_appliances():
        device = request.query.device.lower()
        function = request.query.function.lower()
        parameter = request.query.parameter.lower()

        print("Device:" + device + " , Function:" + function + ", Parameter:" + parameter)

        if device == 'cron':
            return_cron_setting = cron_read()

            # よくわからないからコメントアウト　はここも
            return return_cron_setting
        elif device == 'clear':
            print(commands.getoutput("sudo crontab -r"))

        elif device == 'cron_state':
            cron_state = commands.getoutput("sudo crontab -l")
            return cron_state


        elif device == 'state':
            # クライアントの方で形式が違うとエラーが出て読み込めない。
            # どうしたらいい。
            state = open(STATE_FILE_DIR, "r")
            # jsonをdict形式で読み込む
            state_dict = json.load(state)

            print(state_dict)

            return state_dict
        else:
            path = search_ir_data(device)
            print("IR Data Path: " + path)

            result = ''

            if path == IR_DATA_DIR:
                print("Failed to control.")
                result = 'failure'
            else:
                playIR(path)
                result = 'success'
            return appliances_response_json(device, function, parameter, result)

    @route('/cron')
    def setting_crons():
        device = request.query.device.lower()
        cron_min = int(request.query.cron_min.lower())
        cron_hou = int(request.query.cron_hou.lower())
        cron_time = int(request.query.after_time.lower())
        print(cron_time)

        isAdd = int(request.query.add_cron.lower())

        print(isAdd)

        if device == 'aircon':
            print("Let's go")
            print(cron_write(device,cron_min, cron_hou, cron_time, isAdd))
        elif device == 'light':
            print(cron_write(device,cron_min, cron_hou, cron_time, isAdd))
        elif device == 'wakeup':
            print("OK throw cron write\n")
            print(cron_write(device,cron_min, cron_hou, cron_time, isAdd) + "\n")

    def cron_write(device, cron_min, cron_hou, cron_time, isAdd):
        cron = ""
        add_mode = ""
        # a 追記 ,   w 新規
        cmd = ""

        # after_time
        # 1 ... this_time (この時間に！)
        # 0 ... after_time (この時間後に！)
        # 3 ... なにこれ 多分回避用

        if int(cron_min) == 0 and cron_time == 3:
            cron += '0 '
        else :
            if cron_time == 1:
                cron += str(cron_min) + " "
            else:
                # 現在時刻取得
                now_hou = datetime.now().strftime("%H")
                now_min = datetime.now().strftime("%M")

                # 現在時刻(now_??) と　送られてきた設定時刻(cron_??)を足す
                setting_hou = int(int(now_hou) + cron_hou)
                setting_min = int(int(now_min) + cron_min)

                # オーバーしてたら正しい時刻に計算
                if setting_min >= 60:
                    # 分の計算
                    setting_hou += 1
                    setting_min -= 60
                elif setting_hou >= 24:
                    # 時の計算
                    setting_hou -= 24

                cron += str(setting_min) + " " + str(setting_hou) + " "

        # 0分になってるとき 
        if int(cron_hou) == 0:
            if cron_time != 0:
                cron += '0 '
        else :
            if cron_time != 0:
                # ↑の条件式が無いとここが追加されてしまう。らしいよ俺が言うには
                cron += str(cron_hou) + " "

        # wakeupだったときのcron設定
        if device == 'wakeup':
            setting_cron_min = cron_min - 2;
            setting_cron_hou = cron_hou;

            if setting_cron_min < 0:
                setting_cron_hou = setting_cron_hou - 1;
                setting_cron_min = abs(setting_cron_min - 58);

            letsgo = str(setting_cron_min) + " " + str(setting_cron_hou) + ' ' +  '* * * sudo python /home/pi/House/irm/irm.py -p -f /home/pi/House/irm/irjson/light.json' + '\n' + cron + ' * * * curl -X GET http://192.168.1.8:10080/sound?state=start';
        else:
            letsgo = cron + '* * * ' + "sudo python /home/pi/House/irm/irm.py -p -f /home/pi/House/irm/irjson/" + device + '.json'

        # 書き込みモードの分岐
        if isAdd == 1:
            add_mode = 'a'
            cmd = letsgo + '\n'
        else:
            add_mode = 'w'
            cmd = '\n\n' + letsgo + "\n"

        cron_settings = open(CRON_FILE, add_mode)
        cron_settings.write(cmd)

        cron_settings.close();

        print(commands.getoutput("sudo crontab < /home/pi/House/irm/crontab"))
        print('\n')
        print(commands.getoutput("sudo /etc/init.d/cron restart"))

        letsgo = commands.getoutput("sudo crontab -l")

        # notification to slack
        slack.notify(text="********************************************The cron setting has changed.                Now cron setting is following                   " + letsgo)
        r = requests.get(BIG_MOUTH + "クーロンの設定が変更されました")

        return letsgo

    def cron_read():
        cron_settings = open(CRON_FILE, 'r')
        result = cron_settings.read()
        print(result)
        # slack.notify(text="********************************************Now cron setting is following                 " + result)

        return result

    def MadEYE(device):
        print(device)

        state = open(STATE_FILE_DIR, "r")
        # jsonをdict形式で読み込む
        state_dict = json.load(state)
        print(state_dict)

        # MadEYE
        # 0 ... Device in not opereted.　li ... no light
        # 1 ... Device in operation.     li ... middle light
        # 2 ... Use only device li. It is max volume now.

        if device == "li-single" or device == "li-double":
            print("light")
            # ライトの処理どうしよ。　−２でいけんのかな

            # ステータスの取得
            now_state = state_dict["light"]
            new_state = 0

            # −２をして０以下になるときと否かで分岐
            # やっぱり普通に３つ分岐させる
            if device == "li-single":
                if now_state == 0:
                   new_state = 2
                elif now_state == 1:
                    new_state = 0
                elif now_state == 2:
                    new_state = 1 
            else:
                if now_state == 0:
                    new_state = 1;
                elif now_state == 1:
                    new_state = 2
                elif now_state == 2:
                    new_state == 0

            print(new_state)
            state_dict["light"] = new_state
        else:
            if device == "wakeup" or device == "cron":
                # wakeup, cronだったときは特に何もしない。
                print("wakeup or cron")
            else:
                # それ意外のデバイス
                if state_dict[device] == 1:
                    print(device + "state in operetion.")
                    state_dict[device] = 0
                else:
                    print(device + "state in not operetion.")
                    state_dict[device] = 1

        state = open(STATE_FILE_DIR, "w")
        json.dump(state_dict, state, indent=4)
        state.close()

except:
    slack.notify(text="DCLABO is down!")
    r = requests.get(BIG_MOUTH + "IRMがダウンしました")

    tb = traceback.format_exc()
    print(tb)

run(host='192.168.1.10', port=10080, debug=True)
