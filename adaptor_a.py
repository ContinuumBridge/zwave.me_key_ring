#!/usr/bin/env python
# adaptor_a.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Written by Peter Claydon
#
ModuleName               = "zwave.me_key_ring"
BATTERY_CHECK_INTERVAL   = 21600    # How often to check battery (secs) = 6 hours

import sys
import time
import os
from pprint import pprint
from cbcommslib import CbAdaptor
from cbconfig import *
from twisted.internet import threads
from twisted.internet import reactor

def onOff(value):
    if value == 0:
        return "off"
    else:
        return "on"

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        self.status =           "ok"
        self.state =            "stopped"
        self.apps =             {"number_buttons": [],
                                 "battery": [],
                                 "connected": []}
        self.currentValue =     "0"
        # super's __init__ must be called:
        #super(Adaptor, self).__init__(argv)
        CbAdaptor.__init__(self, argv)
 
    def setState(self, action):
        # error is only ever set from the running state, so set back to running if error is cleared
        if action == "error":
            self.state == "error"
        elif action == "clear_error":
            self.state = "running"
        msg = {"id": self.id,
               "status": "state",
               "state": self.state}
        self.sendManagerMessage(msg)

    def sendCharacteristic(self, characteristic, data, timeStamp):
        msg = {"id": self.id,
               "content": "characteristic",
               "characteristic": characteristic,
               "data": data,
               "timeStamp": timeStamp}
        for a in self.apps[characteristic]:
            self.sendMessage(msg, a)

    def checkBattery(self):
        cmd = {"id": self.id,
               "request": "post",
               "address": self.addr,
               "instance": "0",
               "commandClass": "128",
               "action": "Get",
               "value": ""
              }
        self.sendZwaveMessage(cmd)
        reactor.callLater(BATTERY_CHECK_INTERVAL, self.checkBattery)

    def checkConnected(self):
        if self.updateTime == self.lastUpdateTime:
            self.connected = False
        else:
            self.connected = True
        self.sendCharacteristic("connected", self.connected, time.time())
        self.lastUpdateTime = self.updateTime
        reactor.callLater(SENSOR_POLL_INTERVAL * 2, self.checkConnected)

    def onZwaveMessage(self, message):
        #cbLog("debug", "onZwaveMessage, message: " + str(message))
        if message["content"] == "init":
            self.updateTime = 0
            self.lastUpdateTime = time.time()
            # number_buttons 
            for button in ('1', '2'):
                cmd = {"id": self.id,
                       "request": "get",
                       "address": "1",
                       "instance": button,
                       "commandClass": "32",
                       "value": "level"
                      }
                self.sendZwaveMessage(cmd)
                cmd = {"id": self.id,
                       "request": "get",
                       "address": "1",
                       "instance": button,
                       "commandClass": "32",
                       "value": "srcNodeId"
                      }
                self.sendZwaveMessage(cmd)
            # Battery
            cmd = {"id": self.id,
                   "request": "get",
                   "address": self.addr,
                   "instance": "0",
                   "commandClass": "128"
                  }
            self.sendZwaveMessage(cmd)
            reactor.callLater(60, self.checkBattery)
        elif message["content"] == "data":
            try:
                if message["commandClass"] == "32":
                    if message["value"] == "level":
                        self.currentValue = message["data"]["value"]
                    elif message["value"] == "srcNodeId":
                        if str(message["data"]["value"]) == self.addr:
                            instance = message["instance"]
                            updateTime = message["data"]["updateTime"]
                            if instance == "1":
                                if self.currentValue == 255:
                                    data = {"1": "on"}
                                else:
                                    data = {"3": "on"}
                            elif instance == "2":
                                if self.currentValue == 255:
                                    data = {"2": "on"}
                                else:
                                    data = {"4": "on"}
                            #cbLog("debug", "onZwaveMessage, data: " + data)
                            self.sendCharacteristic("number_buttons", data, time.time())
                elif message["commandClass"] == "128":
                     battery = message["data"]["last"]["value"] 
                     cbLog("info", "battery level: " +  str(battery))
                     msg = {"id": self.id,
                            "status": "battery_level",
                            "battery_level": battery}
                     self.sendManagerMessage(msg)
                     self.sendCharacteristic("battery", battery, time.time())
                else:
                    cbLog("warning", "onZwaveMessage. Unrecognised message: " + str(message))
                self.updateTime = message["data"]["updateTime"]
            except Exception as ex:
                cbLog("warning", "onZwaveMessage. Exception: " + str(message) + " " + str(type(ex)) + " " + str(ex.args))

    def onAppInit(self, message):
        cbLog("debug", "onAppInit, req: " +  str(message))
        resp = {"name": self.name,
                "id": self.id,
                "status": "ok",
                "service": [{"characteristic": "number_buttons", "interval": 0},
                            {"characteristic": "battery", "interval": 600},
                            {"characteristic": "connected", "interval": 600}],
                "content": "service"}
        self.sendMessage(resp, message["id"])
        self.setState("running")

    def onAppRequest(self, message):
        # Switch off anything that already exists for this app
        for a in self.apps:
            if message["id"] in self.apps[a]:
                self.apps[a].remove(message["id"])
        # Now update details based on the message
        for f in message["service"]:
            if message["id"] not in self.apps[f["characteristic"]]:
                self.apps[f["characteristic"]].append(message["id"])
        cbLog("debug", "apps: " + str(self.apps))

    def onAppCommand(self, message):
        if "data" not in message:
            cbLog("warning", "app message without data: " + str(message))
        else:
            cbLog("warning", "This is a sensor. Message not understood: " + str(message)
)
    def onConfigureMessage(self, config):
        """Config is based on what apps are to be connected.
            May be called again if there is a new configuration, which
            could be because a new app has been added.
        """
        self.setState("starting")

if __name__ == '__main__':
    Adaptor(sys.argv)
