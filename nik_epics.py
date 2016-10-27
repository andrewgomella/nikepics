#!/usr/bin/env python
"""
CHANGELOG:
10/01/2013 first version made during government shutdown
11/21/2013 added more error handling, ability to change filetype,
           file location setting
11/22/2013 added ability to change shutter speed
4/2013     too many changes to mention here, mostly improvements,
           moved callbacks from nikonpy to here so pcaspy knows exactly
           when callbacks are issued
4/14/2014  added bulb feature, moved noncamera PV names to global variables at
           top of file
5/26/2014  changed multiple things, add neftotiff, add liveview support,
           add epics imagej support
6/26/2014  changed PV prefix to generalize it with camera name, added more PVs
           (LENS, BATTERY)
           changed implementation of finding the device by adding exception,
           removed self.capture nikonpy object is nicam now
           made PV_LIST global, added sendMail()
6/28/2014  added WIA restart service
6/30/2014  added mail capabilities (beta version), liveview bug fixed
7/04/2014  fixed bug for camera disconnect/connect during scan.
           Beta tested it and it shows promise, added more comments,
           updated the send mail function to reflect scan status.
7/05/2014  removed CaptureComplete()
9/9/2014   changed neftotiff so it uses freeimage (custom compiled),
           works as expected now.
3/24/2015  added new records for ioc admin: HOSTNAME, RECORD_CNT, SysReset
4/01/2015  added more records for ioc admin: STARTTOD, TOD, KERNEL_VERS, UPTIME,
           EPICS_VERS, APP_DIR1, ENGINEER, LOCATION. These records are same as
           devIocStat records to keep consistency
4/06/2015  SysReset record is functional now. Added "nicam" records (RAWCOMPRESS, 
           RAWBIT (TAKEN FROM A.Gomellas implementation) AND FOCUSMODE)
           changed os.path.exists(value) to os.path.isdir(value) to check if 
           path exists and is directory.
4/21/15    Added sync support for oxford series micro focus x-ray source. 
           Updated qt screen as well       
4/23/15    Fixed bug in raw bit depth and raw compression update, Removed un
           necessary wait
5/04/16    All input records are postfixed with RBV. This is so that the auto
           build of the request file only include output reccords. Please follow
           this convention for future addition of new records. Removed old method
           of autosave restore (using pickle). Now uses epics.autosave. For TIFFFILEPATH & FILEPATH records
           setParam condition is changed such that if value != '' and value[-1] != '\\' then 
           append '\\' at the end of value.
7/10/16    Clean ioc exit on keyboard interrupt, more generic way to add utils dir to sys.path 

"""
import platform, os, sys
if platform.architecture()[0] == '32bit':
     md3_path = os.getcwd() + '\\' + 'x86' + '\\' + 'md3' + '\\'
     python_net_path = os.path.abspath(os.getcwd()) + '\\' + 'x86' + '\\' + 'pythonnet' + '\\'
     libraw_path = os.path.abspath(os.getcwd()) + '\\' + 'x64' + '\\' + 'libraw' + '\\'
     sys.path.append(os.path.abspath(python_net_path))
     sys.path.append(os.path.abspath(libraw_path))
elif platform.architecture()[0] == '64bit':
     md3_path = os.getcwd() + '\\' + 'x64' + '\\' + 'md3' + '\\'
     python_net_path = os.path.abspath(os.getcwd()) + '\\' + 'x64' + '\\' + 'pythonnet' + '\\'
     libraw_path = os.path.abspath(os.getcwd()) + '\\' + 'x64' + '\\' + 'libraw' + '\\'
     sys.path.append(os.path.abspath(python_net_path))
     sys.path.append(os.path.abspath(libraw_path))
else:
    print ".NET not found!"
    sys.exit()
import clr
try:
    clr.AddReference('nikoncswrapper')
except Exception as e:
    print e
    sys.exit()
import Nikon
from pcaspy.driver import manager
from pcaspy import SimpleServer, Driver
import System.IO, nikonpy, time, threading, usb, re
from epics import caput, caget, PV
import epics
import neftotiff
import cv2 as cv
import multiprocessing as mp
import numpy as np
#import win32serviceutil
import code, datetime, logging
sys.path.append(os.path.realpath('../utils'))
try:
    import epicsApps
    epicsApps_found = True
except ImportError:
    epicsApps_found = False
    logging.warning('Module epicsApps not found.')
    pass

"""
Epics variables not controlled by this nikon epics server (IOC):
1. X-ray
2. Scan record
3. Any other motor records
"""
# Please change this accordingly to your PV's
EXPERIMENT = 'CEL:'

XRAY_IOC                      = EXPERIMENT  + 'OXFORD:xray:'
SCAN_IOC                      = EXPERIMENT  + 'SCAN:'
MOTOR_IOC                     = EXPERIMENT  + 'NEWPORT:'
 
SCAN_MSG_IOC                  = PV(SCAN_IOC + 'scan1.SMSG', callback=True)
SCAN_DETECTOR_1               = PV(SCAN_IOC + 'scan1.T1PV', callback = False)
SCANPROGRESS_IOC              = SCAN_IOC + 'scanProgress:'
NFINISHED                     = PV(SCANPROGRESS_IOC+'Nfinished')
NTOTAL                        = PV(SCANPROGRESS_IOC+'Ntotal')

# X-ray current deadband value, x-ray wil1 (approx) not be considered "on" until this value is reached
XRAY_DEADBAND = 10
POLL_TIME = 0.001

# If DOC is ON (1) save motor pv's.
MOTOR_IOC_LIST = [
                    MOTOR_IOC + 'm1',  MOTOR_IOC + 'm2',  MOTOR_IOC + 'm3', \
                    MOTOR_IOC + 'm4',  MOTOR_IOC + 'm5',  MOTOR_IOC + 'm6', \
                 ]
               
PV_LIST = MOTOR_IOC_LIST

def nothing(x):
    """
    OpenCV for some reason requires this empty function
    """
    pass

# Nikon camera enum list. Epics enums are limited to 16 enums only
nikenums = ['FILE_TYPE', 'JPEGSIZE', 'ISO', 'APERTURE', 'SHUTTER']
pvdb = {
    ######################################################
    # Values relating to connecting/ disconnecting/ status
    ######################################################
#   PV base names              VALUES
    'INIT_RBV'           : {'asyn' : True},
    'DEINIT_RBV'         : {},
    'INITSTAT_RBV'       : {'type' : 'enum',
                            'enums': ['false', 'true']},
    'STATUS_RBV'         : {'type' : 'enum',
                            'enums': ['IDLE', 'CAPTURING', 'CONNECTING', \
                                      'DISCONNECTED', 'WAITXRAY'],
                            'value': 3},
    'CAMERA_NAME_RBV'    : {'type' : 'string'},
    'BATTERY'            : {'type' : 'int',
                            'scan' : 60},
    'LENS_RBV'               : {'type' : 'string'},
    'BULBTIMER'          : {},
    'BULBCOUNTDOWN_RBV'  : {},
    'XSYNC'              : {'type' : 'enum',
                            'enums': ['NONE', 'SRI', 'OXFORD', 'CPI']},
    'XSYNC_RBV'          : {'type'  : 'enum',
                            'enums' : ['NONE', 'SRI', 'OXFORD', 'CPI'],
                            'scan' : 1},
    'DOC'                : {'type' : 'enum',
                            'enums': ['OFF', 'ON']},
    #################################
    # Values relating to image saving
    #################################
    'SAVEIMG'            : {'type' : 'enum',
                            'enums': ['OFF', 'ON']},
    'FILENAME'           : {'type' : 'string',},
    'FILENAMEEXISTS_RBV' : {'type' : 'enum',
                            'enums': ['false', 'true'],
                            'scan' : 1},
    'FILEPATH'           : {'type' : 'string',},
    'FILEPATHEXISTS_RBV' : {'type' : 'enum',
                            'enums': ['false', 'true'],
                            'scan' : 1},
    'FILENUM'            : {'type' : 'int'},
    'AUTOINCR'           : {'type' : 'enum',
                            'enums': ['false', 'true']},
    'LASTFILE_RBV'       : {'type' : 'string'},
    'SHUTTER_INDEX'      : {'type' : 'int'},
    'SHUTTER_INDEXSTRING': {'type' : 'string'},
    ####################
    # Nikon camera enums
    ####################
    'APERTURE'           : {'type' : 'enum'},
    'SHUTTER'            : {'type' : 'enum'},
    'ISO'                : {'type' : 'enum'},
    'JPEGSIZE'           : {'type' : 'enum'},
    'FILE_TYPE'          : {'type' : 'enum'},
    'EXPMODE'            : {'type' : 'enum'},
    'RAWBIT'             : {'type' : 'enum',
                            'enums': ['12 bit', '14 bit'] },
    'RAWCOMPRESS'        : {'type' : 'enum',
                            'enums': ['Uncompressed', 'Compressed', 'Lossless Compressed']},
    #######################################################
    # Values relating to Nef to Tiff conversion with libraw
    #######################################################
    'NEFTOTIFF'          : {'type' : 'enum',
                            'enums': ['OFF', 'ON']},
    'TIFFFILEPATH'       : {'type' : 'string'},
    'GREEN'              : {'type' : 'enum',
                            'enums': ['OFF', 'ON']},
    'X0CROP'             : {'type' : 'int'},
    'Y0CROP'             : {'type' : 'int'},
    'XSIZE'              : {'type' : 'int'},
    'YSIZE'              : {'type' : 'int'},
    'BIN'                : {'type' : 'int'},
    ##################################
    # Values relating to imagej plugin
    ##################################
    'IMAGEJ'             : {'type' :'enum',
                            'enums': ['OFF''ON']},
    'PIC:ArrayData_RBV'      : {'type' :'int',
                            'prec' : 0},
    'PIC:DATA_TYPE_RBV'  : {},
    'PIC:COLOR_MODE'     : {'value':'NDColorModeMono'},
    'PIC:ArraySize0_RBV' : {'value': 640},
    'PIC:ArraySize1_RBV' : {'value': 360},
    'PIC:ArraySize2_RBV' : {'value': 1},
    'PIC:ColorMode_RBV'  : {},
    'PIC:UniqueId_RBV'   : {'value': 1},
    ########################################
    # Values relating to capture/live view/
    ########################################
    'FIRE'               : {},
    'LV'                 : {'type' : 'int'},
    'FOCUSMODE_RBV'      : {'type' : 'enum',
                            'enums': ['AUTO-SINGLE', 'AUTO-CONTINOUS', 'AUTO', \
                                      'HARD MANUAL', 'SOFT MANUAL'],},
   }

if epicsApps_found == True:
    pvdb.update(epicsApps.pvdb)

class myDriver(Driver):

    def __init__(self):
        super(myDriver, self).__init__()
        for i in nikenums:
            manager.pvs['default'][i].info.enums = nicam.getenumlist(i)
        # initialize static pv's 
        self.up_time_mm = 0
        self.up_time_hh = 0
        nicam.manager.DeviceAdded += self.DeviceAdded
        nicam.manager.DeviceRemoved += self.DeviceRemoved
        nicam._device.ImageReady += self.ImageReady
        self.setParam('STATUS_RBV', 0)
        self.setParam('INITSTAT_RBV', 1)
        self.setParam('CAMERA_NAME_RBV', str(prefix))
        self.getinfo()
        self.documentString = ''
        self.imgconvert = neftotiff.neftotiff()
        # Set scan detector as camera 
        SCAN_DETECTOR_1.put(prefix + 'FIRE')
        if epicsApps_found == True:
            pvdb.update(epicsApps.pvdb)
            self.iocStats()
            epicsApps.buildRequestFiles(prefix, pvdb.keys(), os.getcwd())
            epicsApps.makeAutosaveFiles()
        self.updatePVs()
        print "Using " + platform.architecture()[0] + " python\nmd3_path = " +  md3_path + "\npython_net_path = " + python_net_path + "\n"
        print '############################################################################'
        print '## NIKEPICS PCAS IOC Online $Date:' + str(datetime.datetime.now())[:-3]
        print '############################################################################'
    
    def iocStats(self):
        """
        sets the iocAdmin related records
        """
        self.start_time = datetime.datetime.now()
        self.setParam('ENGINEER', 'Andrew Gomella')
        self.setParam('LOCATION', 'B1D521D SVR-SMWIN122')
        self.setParam('RECORD_CNT', len(pvdb.keys()))
        self.setParam('APP_DIR1', str(os.getcwd()))
        self.setParam('UPTIME', str(self.start_time))
        self.setParam('PARENT_ID', os.getpid())
        self.setParam('HEARTBEAT', 0)    

    def write(self, reason, value):
        if reason == 'FIRE' and value == 1:
            # Set status to idle and make sure camera is connected before firing
            if self.getParam('INITSTAT_RBV') == 1 and self.getParam('STATUS_RBV') == 0:
                self.tid = threading.Thread(target=self.capt, args=())
                self.tid.daemon = True
                self.tid.start()
        if reason == 'LV':
            self.setParam(reason, value)
            self.tid = threading.Thread(target=self.lv, args=(value, ))
            self.tid.daemon = True
            self.tid.start()
        elif reason == 'INIT_RBV':
            if self.getParam('INITSTAT_RBV') == 0:
                self.tid = threading.Thread(target=self.init, args=())
                self.tid.daemon = True
                self.tid.start()
        # Currently Shutter index is not used. Trying to find a better way to display all nikon enums
        elif reason == 'SHUTTER_INDEX':
            if self.getParam('INITSTAT_RBV') == 1 and self.getParam('STATUS_RBV') == 0:
                nicam.setenum('SHUTTER', value)
        # setting all nikon enums
        elif reason == 'FILE_TYPE' or reason == 'SHUTTER' or \
             reason == 'JPEGSIZE' or reason == 'ISO':
            if self.getParam('INITSTAT_RBV') == 1 and self.getParam('STATUS_RBV') == 0:
                nicam.setenum(reason, value)
        elif reason == "DEINIT_RBV" and value == 1:
            self.deinit()
        # set filepath here
        elif reason == "FILEPATH":
            self.setParam(reason, value)
            if value != '' and value[-1] != '\\':
                caput(prefix + 'FILEPATH', value + '\\')
            if os.path.isdir(value):
                self.setParam("FILEPATHEXISTS_RBV", 1)
            else:
                self.setParam("FILEPATHEXISTS_RBV", 0)
       # set tiff filepath here
        elif reason == "TIFFFILEPATH":
            self.setParam(reason, value)
            if value != '' and value[-1] != '\\':
                caput(prefix + 'TIFFFILEPATH', value + '\\')
        elif reason == "FILENAME":
            self.setParam(reason, value)
            if value != '' and value[-1] != '_':
                caput(prefix + 'FILENAME', value + '_')
            self.setParam('FILENUM', 0)
            fp = self.getParam('FILEPATH')
            fn = str(int(self.getParam('FILENUM')))
            if os.path.exists(fp + value + fn + '.jpg'):
                self.setParam("FILENAMEEXISTS_RBV", 1)
            elif os.path.exists(fp+value + fn + '.nef'):
                self.setParam("FILENAMEEXISTS_RBV", 1)
            else:
                self.setParam("FILENAMEEXISTS_RBV", 0)
        elif reason == 'RAWBIT':
            nicam.setBit(value)
            self.setParam(reason, value)    
        elif reason == "RAWCOMPRESS":
            nicam.setCompress(value)
            self.setParam(reason, value)
        elif reason == "XSYNC":
           self.setParam(reason, value)
        else:
            self.setParam(reason, value)
        self.setParam(reason, value)
        self.updatePVs()
        self.getinfo()

    def lv(self, value):
        if value == 1:
            nicam.startlv()
            self.lid = threading.Thread(target=self.updateLV, args=())
            self.lid.daemon = True
            self.lid.start()
        if value == 0:
            nicam.stoplv()
            
    def read(self, reason):
        format_time = ""
        global XRAY_IOC   
        if reason == 'UPTIME':
            format_time = datetime.datetime.now() - self.start_time
            value  = str(format_time).split(".")[0] 
        elif reason == 'TOD':
            value = str(datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"))    
        elif reason == 'HEARTBEAT':
            value = self.getParam('HEARTBEAT') + 1
            self.setParam('HEARTBEAT', value)
        elif reason == 'XSYNC_RBV':
            value = self.getParam('XSYNC')
            if value == 3:
              XRAY_IOC = EXPERIMENT + 'cpiSync:'  
            elif value == 2:
                XRAY_IOC = EXPERIMENT + 'OXFORD:xray:'
            elif value == 1:
                XRAY_IOC = EXPERIMENT + 'SRI:xray:'
            elif value == 0:
                XRAY_IOC = ''
        # This is D800 specific
        elif reason == 'FOCUSMODE_RBV':
            value = nicam.getFocusMode()
        elif reason == 'FILEPATHEXISTS_RBV':
            if os.path.isdir(self.getParam('FILEPATH')):
                value = 1
            else:
                value = 0
        elif reason ==  'FILENAMEEXISTS_RBV':
            fp = self.getParam('FILEPATH')
            fn = str(int(self.getParam('FILENUM')))
            if os.path.exists(fp + self.getParam('FILENAME') + fn + '.jpg') or \
               os.path.exists(fp+ self.getParam('FILENAME') + fn + '.nef'):
                value = 1
            else:
                value = 0
        else: 
            value = self.getParam(reason)
        return value
  
    def updateLV(self):
        self.setParam('PIC:ArraySize0_RBV', 640)
        self.setParam('PIC:ArraySize1_RBV', 360)
        cv.namedWindow('LV', cv.WINDOW_NORMAL)
        cv.createTrackbar('B/C', 'LV', 0, 1, nothing)
        cv.createTrackbar('B', 'LV', 1, 200, nothing)
        cv.createTrackbar('C', 'LV', 1, 100, nothing)
        cv.createTrackbar('Canny', 'LV', 0, 1, nothing)
        cv.createTrackbar('Ca Threshold', 'LV', 1, 100, nothing)
        cv.createTrackbar('Hough', 'LV', 0, 1, nothing)
        cv.createTrackbar('Min inter', 'LV', 100, 300, nothing)
        cv.createTrackbar('Min line', 'LV', 1, 300, nothing)
        cv.createTrackbar('Max line', 'LV', 1, 300, nothing)
        self.b = 1
        self.c = 1
        self.MinInter = 150
        self.ca = 50

        while self.getParam('LV') == 1:
            self.b = cv.getTrackbarPos('B', 'LV')
            self.c = cv.getTrackbarPos('C', 'LV')
            self.ca = cv.getTrackbarPos('Ca Threshold', 'LV')
            self.max = cv.getTrackbarPos('Max line', 'LV')
            self.min = cv.getTrackbarPos('Min line', 'LV')
            self.MinInter = cv.getTrackbarPos('Min inter', 'LV')
            lvimage = nicam.getLV()
            img = cv.imdecode(np.fromiter(lvimage.JpegBuffer, np.int8), 0)
            # img = cv.resize(img, (0,0), fx=2, fy=2)
            # brightness and contrast
            if cv.getTrackbarPos('B/C', 'LV') == 1:
                npim2 = cv.multiply(img, self.c*.05)
                img = cv.add(npim2, self.b)
            # canny edges demo
            if cv.getTrackbarPos('Canny', 'LV') == 1:
                img = cv.GaussianBlur(img, (3, 3), 0)
                lapla = cv.Laplacian(img, cv.CV_16S, ksize=3, scale=1, delta=0)
                img = cv.convertScaleAbs(lapla)
            # hough lines demo
            elif cv.getTrackbarPos('Hough', 'LV') == 1:
                try:
                    #detected_edges = cv.GaussianBlur(img,(3,3),0)
                    detected_edges = cv.Canny(img, self.ca, self.ca*0.3, \
                                              apertureSize=3)
                    lines = cv.HoughLinesP(detected_edges, 1, np.pi/180, 150, \
                                           minLineLength=self.min, \
                                           maxLineGap=self.max)

                    for x1, y1, x2, y2 in lines[0]:
                        cv.line(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv.imshow('LV', img)
                except:
                    print "no lines"

            self.yid = threading.Thread(target=self.lvdecode, args=(img, ))
            self.yid.daemon = True
            self.yid.start()
            cv.imshow('LV2', img)
            cv.waitKey(1)
        cv.destroyAllWindows()

    def lvdecode(self, img):
        self.setParam('PIC:ArrayData_RBV', img)
        self.setParam('PIC:UniqueId_RBV', self.getParam('PIC:UniqueId_RBV')+1)
        self.callbackPV('PIC:UniqueId_RBV')
        self.updatePVs()
        
    def startXray(self):
        """
        Returns when the xray is on and outputting x-rays at set values
        """
        if self.getParam('XSYNC') == 3: # x-ray sync is set to cpi-cmp200
            self.myFlag = 0
            self.setParam('STATUS_RBV', 4)
            # check that the x-ray is not disconnected or in init phase or the emergency stop is on
            if caget(EXPERIMENT + 'CPI:xray:GeneratorStatus') == 0 or \
               caget(EXPERIMENT + 'CPI:xray:GeneratorStatus') == 1 or \
               caget(EXPERIMENT + 'CPI:xray:GeneratorStatus') == 9:
                   self.myFlag = 1
                   return
            else:
                # here we just get the generator ready to expose
                caput(XRAY_IOC + 'RAD_PREP' , 1)
                while (caget(EXPERIMENT + 'CPI:xray:' + 'RadPrep') != 2 and 
                       caget(EXPERIMENT + 'CPI:xray:ErrorLatching') != 22):
                    time.sleep(0.01)
                if caget(EXPERIMENT + 'CPI:xray:ErrorLatching') == 22:
                    self.myFlag = 1
                    caput(EXPERIMENT + 'CPI:xray:AcknowledgeError', 1)
                    
        elif self.getParam('XSYNC') == 2: # x-ray sync is set to oxford/nova
            self.setParam('STATUS_RBV', 4)
            if caget(XRAY_IOC + 'STATUS_RBV') == 5: # make sure x-ray is not in fault mode.
                print str(datetime.datetime.now())[:-3], 'X-ray is in fault mode!'
                return
            else:
                if caget(XRAY_IOC + 'STATUS_RBV') == 0: # xray is warming
                    print str(datetime.datetime.now())[:-3], 'Waiting for warm up to finish!'
                    return
                if caget(XRAY_IOC + 'STATUS_RBV') == 1: # if xray in standby mode 
                    # turn on x-ray 
                    caput(XRAY_IOC + 'ON', 1)
                    # wait for x-ray to reach set points
                    while (caget(XRAY_IOC + 'FIRING_RBV') != 1): # this record is sampled at 10Hz in the db
                        time.sleep(0.01)
                elif caget(XRAY_IOC + 'STATUS_RBV') == 3 or caget(XRAY_IOC + 'STATUS_RBV') == 2: # in pulse/output mode now.
                    caput(XRAY_IOC + 'PULSE_MODE', 0)   
                    while (caget(XRAY_IOC + 'FIRING_RBV') != 1):
                        time.sleep(0.01)
                print str(datetime.datetime.now())[:-3], 'X-ray is outputting at set points'
        elif self.getParam('XSYNC') == 1: # x-ray sync is set to sri
            self.setParam('STATUS_RBV', 4)
            caput(XRAY_IOC + 'ON', 1) 
            print str(datetime.datetime.now())[:-3], 'X-ray is outputting at set points'
        elif self.getParam('XSYNC') == 0:
            print str(datetime.datetime.now())[:-3], 'Acquiring dark image!'  
            
    def stopXray(self):
        """
        Stop x-ray flux
        """
        if self.getParam('XSYNC') == 0:
            return
        elif self.getParam('XSYNC') == 1: # x-ray sync is set to sri
            caput(XRAY_IOC + 'ON', 0)
        elif self.getParam('XSYNC') == 2: # x-ray sync is set to oxford
            caput(XRAY_IOC + 'ON', 0)
        elif self.getParam('XSYNC') == 3: # x-ray sync is set to cpi-cmp200
            caput(XRAY_IOC + 'EXPOSE', 0)
            time.sleep(.01)
            caput(XRAY_IOC + 'RAD_PREP', 0)
        print str(datetime.datetime.now())[:-3], 'X-ray is off'
                 
    def capt(self):
        self.setParam('LV', 0)
        if self.getParam('DOC') == 1:
            self.updateDocumentString()
        self.startXray()
        if self.getParam('XSYNC') == 3 and self.myFlag != 1:
            caput(XRAY_IOC +'EXPOSE', 1)
        elif self.getParam('XSYNC') == 3 and self.myFlag == 1:
            print str(datetime.datetime.now())[:-3], 'Acquiring dark image, Please turn emergency stop off'
        self.setParam('STATUS_RBV', 1)
        # test for bulb capture mode, if not do normal capture
        if self.getParam('SHUTTER') == 1:
            stop = time.time() + self.getParam('BULBTIMER')
            nicam.bulbcapstart()
            while time.time() < stop:
                self.setParam('BULBCOUNTDOWN_RBV', stop-time.time())
                self.updatePVs()
            nicam.bulbcapstop()
        else:
            nicam.cap()
        self.updatePVs()

    def updateDocumentString(self):
        #returns a list of all pv values in pvDict into a string ready for output to txt file, but does not write text file
        for pvName in PV_LIST:
            self.documentString += pvName + ' - ' + str(caget(pvName)) + '\n'

    def getinfo(self):
        try:
            if self.getParam('INITSTAT_RBV') == 1 and self.getParam('STATUS_RBV') == 0:
#                nicam.lockFocus()
                for enum in nikenums:
                    self.setParam(enum, nicam.getenumindex(enum))
                self.setParam('SHUTTER_INDEXSTRING', nicam.getenumstring('SHUTTER'))
                self.setParam('BATTERY', (nicam.getBattery()))
                self.setParam('LENS_RBV', str(nicam.getLensInfo()))
                self.updatePVs()
        except Nikon.NikonException as ex:
            print ex.Message

    def init(self):
       # set status to 'CONNECTING'
        self.setParam('STATUS_RBV', 2)
        self.updatePVs()
       # create the nikonpy object again
        nicam = nikonpy.nikonpython(md3_path +  mdname)
        nicam.manager.DeviceAdded += self.DeviceAdded
        nicam.manager.DeviceRemoved += self.DeviceRemoved
        nicam.connect()

    def deinit(self):
        self.setParam('CAMERA_NAME_RBV', 'None')
        self.setParam('INITSTAT_RBV', 0)
        self.setParam('STATUS_RBV', 3)
        self.updatePVs()
#        nicam.Exit()

    def postarray(self, image):
        img = cv.imdecode(np.fromiter(image.Buffer, np.int8), 0)
        self.setParam('PIC:ArraySize1_RBV', img.shape[0])
        self.setParam('PIC:ArraySize0_RBV', img.shape[1])
        self.setParam('PIC:ArrayData_RBV', img)
        self.setParam('PIC:UniqueId_RBV', self.getParam('PIC:UniqueId_RBV')+1)
        self.callbackPV('PIC:UniqueId_RBV')
        self.updatePVs()

#   These functions allow the nikonpy (nikoncswrapper) to communicate about status with the program
    def DeviceAdded(self, sender, device):
        self.callbackPV('INIT_RBV')
        print "Device added!", time.strftime("%H:%M:%S")
#       Notify that the device is connected
        self.setParam('INITSTAT_RBV', 1)
#       Set status to idle
        self.setParam('STATUS_RBV', 0)
        self.setParam('CAMERA_NAME_RBV', str(nicam.getDeviceName()))
        self.setParam('LENS_RBV', str(nicam.getLensInfo()))
        self.getinfo()
        self.updatePVs()
        # check if scan is running, which means the device disconnected during the scan -try to recover
        if caget(SCANPROGRESS_IOC +'running') == 1:
            print "Camera reconnected during scan, attempting to recover"
            if SCAN_MSG_IOC.get() == "Waiting for client":
                print SCAN_MSG_IOC.get()
                self.setParam('FIRE', 0)
                nicam._device.ImageReady += self.ImageReady
                self.capt()

    def DeviceRemoved(self, sender, device):
        print "Device removed!", time.strftime("%H:%M:%S")

        if self.getParam('XSYNC') == 1:
            caput(XRAY_IOC + 'ON', '0')
            while caget(XRAY_IOC + 'UA_RBV') > 100:
                time.sleep(.01)
#       Reset Camera name to None
        self.setParam('CAMERA_NAME_RBV', 'None')
#       Reset Lens type to None
        self.setParam('LENS_RBV', 'None')
#       Notify that device is disconnected
        self.setParam('INITSTAT_RBV', 0)
#       set status to disconnected
        self.setParam('STATUS_RBV', 3)
        self.updatePVs()

    def ImageReady(self, sender, image):
        if self.getParam('XSYNC') == 3:
            caput(XRAY_IOC + 'EXPOSE' , 0)
        print str(datetime.datetime.now())[:-3], 'Image Ready'
        # if not scanning or scanning and all images acquired then go back to standby mode.
        if caget(SCANPROGRESS_IOC +'running') == 1:
            # check if all images from scan are done. 
            if (NFINISHED.get() + 1 == NTOTAL.get()):
                self.stopXray()
        else:
            self.stopXray()
        ###############################
        # Determine Filename and type
        ###############################
        num = int(self.getParam('FILENUM'))
        pathname = self.getParam('FILEPATH') + \
        self.getParam('FILENAME') + str(num)
        if image.Type == Nikon.NikonImageType.Jpeg:
            writename = pathname + ".jpg"
        elif image.Type == Nikon.NikonImageType.Raw:
            writename = pathname + ".nef"
        else:
            writename = pathname + ".tiff"
        if os.path.exists(writename):
            print "Warning filename already exists- Overwriting!"
        ################################
        # Write file directly from camera
        ################################
        if self.getParam('SAVEIMG') == 1:
            self.savecamfile(image, writename)
        elif image.Type == Nikon.NikonImageType.Raw & \
             self.getParam('NEFTOTIFF') == 1:
            self.savecamfile(image, writename)
        ################################
        # Write 16bit linear tiff
        ################################
        if self.getParam('NEFTOTIFF') == 1 & image.Type == Nikon.NikonImageType.Raw:
            try:
                if self.getParam('TIFFFILEPATH') == '':
                    tiffpathname = self.getParam('FILEPATH') + \
                    self.getParam('FILENAME') + str(num)
                else:
                    tiffpathname = self.getParam('TIFFFILEPATH') + \
                    self.getParam('FILENAME') + str(num)
                self.nid = mp.Process(target=self.imgconvert.ntt, \
                           args=(writename, writename, \
                           self.getParam('SAVEIMG'), tiffpathname+".tif", \
                           self.getParam('YSIZE'), self.getParam('XSIZE'), \
                           self.getParam('Y0CROP'), self.getParam('X0CROP'), \
                           self.getParam('BIN'), self.getParam('GREEN')))
                self.nid.start()
            except Exception as e:
                self.imgconvert = None
                print "nef conversion failed", e
                if self.getParam('SAVEIMG') == 0:
                    print "saving nef as backup"
                    s = System.IO.FileStream(writename, System.IO.FileMode.Create, System.IO.FileAccess.Write)
                    s.Write(image.Buffer, 0, image.Buffer.Length)
                    s.Close()
        ###############################
        # Post Array data
        ###############################
        if self.getParam('IMAGEJ') == 1:
            if self.getParam('FILE_TYPE') in [0, 1, 2]:
                self.lid = threading.Thread(target=self.postarray, args=(image, ))
                self.lid.daemon = True
                self.lid.start()
        ################################
        # Update relevant pvs, document
        ################################
        if self.getParam('DOC') == 1:
            if self.getParam('SAVEIMG') == 1:
                f = open(pathname + '.txt', 'w')
                f.write(self.documentString)
            if self.getParam('NEFTOTIFF') == 1:
                f = open(tiffpathname + '.txt', 'w')
                f.write(self.documentString)
            self.documentString = ''
        self.setParam('STATUS_RBV', 0)
        if self.getParam('AUTOINCR') == 1:
            self.setParam('FILENUM', num + 1)
        self.setParam('LASTFILE_RBV', writename)
        self.setParam('FIRE', 0)
        caput(SCAN_IOC + 'scan1.WAIT', 0)
        caput(SCAN_IOC + 'scan2.WAIT', 0)
        caput(SCAN_IOC + 'scan3.WAIT', 0)
        self.updatePVs()

    def savecamfile(self, image, name):
        try:
            s = System.IO.FileStream(name, System.IO.FileMode.Create, System.IO.FileAccess.Write)
            s.Write(image.Buffer, 0, image.Buffer.Length)
            s.Close()
            print str(datetime.datetime.now())[:-3], 'Camera Image Saved!'
        except:
            print "Save Camera File Failed- out of disk space?"


if __name__ == '__main__':
    # First restart WIA service. Need to run script as admin to do this
#    service = 'stisvc'
#    win32serviceutil.RestartService(service, None)
#    print '%s started successfully' % service
    # Find the nikon camera model attached and choose appropriate .md3 file
    myState = 0
    for dev in usb.core.find(find_all=True):
        # print dev.idVendor, dev.idProduct
        try:
            if dev.idVendor == 1200 and dev.idProduct == 1056:
                print "Nikon D3X found\nNote: Bulb mode not supported"
                mdname = "Type0002.md3"
                myState = 1
            elif dev.idVendor == 1200 and dev.idProduct == 1072:
                print "Nikon D7100 found"
                mdname = "Type0010.md3"
                myState = 1
            elif dev.idVendor == 1200 and dev.idProduct == 1058:
                print "Nikon D700 found\nNote: Bulb mode not supported"
                mdname = "Type0001.md3"
                myState = 1
            elif dev.idVendor == 1200 and dev.idProduct == 1066:
                print "Nikon D800 found"
                mdname = "Type0006.md3"
                myState = 1 
            elif dev.idVendor == 1200 and dev.idProduct == 1079:
                print "Nikon D750 found"
                mdname = "Type0015.md3"
                myState = 1
            if myState == 1:
                raise StopIteration
        except StopIteration:
            break
    if myState == 0:
        print "No Nikon camera found.\nEnsure cable is connected," +  \
              "camera is powered on, and you have the proper md3 file for your camera."
        mdname = ''
        sys.exit()
    print md3_path + mdname
    nicam = nikonpy.nikonpython(md3_path + mdname)
    prefix = EXPERIMENT + nicam.getDeviceName() + ':'

    numbers = re.findall('\d+', nicam.getenumlist('JPEGSIZE')[0])
    size = int(numbers[0])*int(numbers[1])
#   print numbers, size
    pvdb['PIC:ArrayData_RBV']['count'] = size # for live view use 230400
    pvdb['PIC:ArraySize0_RBV']['value'] = int(numbers[0])
    pvdb['PIC:ArraySize1_RBV']['value'] = int(numbers[1])

    if nicam.getboolean('NOISERED') == True:
        print 'WARNING: In-camera noise reduction is turned on'
    server = SimpleServer()
    server.createPV(prefix, pvdb)
    driver = myDriver()
    # process CA transactions
    while True:
        try:
            server.process(0.01)
        except KeyboardInterrupt:
            try:
                sys.exit(0)
            except SystemExit:
                os._exit(0)
    