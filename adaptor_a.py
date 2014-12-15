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
import logging
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
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
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
        logging.debug("%s %s state = %s", ModuleName, self.id, self.state)
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
        #logging.debug("%s %s onZwaveMessage, message: %s", ModuleName, self.id, str(message))
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
                    if message["data"]["name"] == "level":
                        self.currentValue = message["data"]["value"]
                    elif message["data"]["name"] == "srcNodeId":
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
                            #logging.debug("%s %s onZwaveMessage, data: %s", ModuleName, self.id, data)
                            self.sendCharacteristic("number_buttons", data, time.time())
                elif message["commandClass"] == "128":
                     #logging.debug("%s %s onZwaveMessage, battery message: %s", ModuleName, self.id, str(message))
                     battery = message["data"]["last"]["value"] 
                     logging.info("%s %s battery level: %s", ModuleName, self.id, battery)
                     msg = {"id": self.id,
                            "status": "battery_level",
                            "battery_level": battery}
                     self.sendManagerMessage(msg)
                     self.sendCharacteristic("battery", battery, time.time())
                else:
                    logging.warning("%s onZwaveMessage. Unrecognised message: %s", ModuleName, str(message))
                self.updateTime = message["data"]["updateTime"]
            except Exception as ex:
                logging.warning("%s onZwaveMessage. Exception: %s %s %s", ModuleName, str(message), type(ex), str(ex.args))

    def onAppInit(self, message):
        logging.debug("%s %s %s onAppInit, req = %s", ModuleName, self.id, self.friendly_name, message)
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
        #logging.debug("%s %s %s onAppRequest, message = %s", ModuleName, self.id, self.friendly_name, message)
        # Switch off anything that already exists for this app
        for a in self.apps:
            if message["id"] in self.apps[a]:
                self.apps[a].remove(message["id"])
        # Now update details based on the message
        for f in message["service"]:
            if message["id"] not in self.apps[f["characteristic"]]:
                self.apps[f["characteristic"]].append(message["id"])
        logging.debug("%s %s %s apps: %s", ModuleName, self.id, self.friendly_name, str(self.apps))

    def onAppCommand(self, message):
        #logging.debug("%s %s %s onAppCommand, req = %s", ModuleName, self.id, self.friendly_name, message)
        if "data" not in message:
            logging.warning("%s %s %s app message without data: %s", ModuleName, self.id, self.friendly_name, message)
        else:
            logging.warning("%s %s %s This is a sensor. Message not understood: %s", ModuleName, self.id, self.friendly_name, message)

    def onConfigureMessage(self, config):
        """Config is based on what apps are to be connected.
            May be called again if there is a new configuration, which
            could be because a new app has been added.
        """
        #logging.debug("%s onConfigureMessage, config: %s", ModuleName, config)
        self.setState("starting")

if __name__ == '__main__':
    Adaptor(sys.argv)
