#based on nikoncswrapper's demo_capture program
# CHANGE LOG:
# 6/25/2014: added getBattery(), getDeviceName(), getLensInfo()
#            Removed getenumstring(), added in-code comments, Some stylistic
#            changes.
# 6/26/2014: added getenumstring()
# 7/04/2014: added deviceImageReady()

import clr
clr.AddReference('nikoncswrapper')
import Nikon
import threading
import sys

class nikonpython():
    def __init__(self, mdname):
        print ' 1'
        self._waitForDevice = threading.Event()    
        self._waitForCapture = threading.Event()
        self.filename = 'File Name'
        try:
            self.manager = Nikon.NikonManager(mdname)
#           Listen for device added event
            self.manager.DeviceAdded += Nikon.DeviceAddedDelegate(self.manager_DeviceAdded)
            self._waitForDevice.wait()
            self.manager.DeviceRemoved += Nikon.DeviceRemovedDelegate(self.manager_DeviceRemoved)
        except Nikon.NikonException as ex:
            print ex.Message
            sys.exit()

#   Enum capabilities only
    def getcapname(self, alias):
        if alias == 'SHUTTER' or alias == 'SHUTTER0' or alias == 'SHUTTER1' or alias == 'SHUTTER2' or alias == 'SHUTTER3':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_ShutterSpeed
        elif alias == 'ISO' or alias == 'ISO0' or alias == 'ISO1':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_Sensitivity
        elif alias == 'APERTURE' or alias == 'APERTURE0' or alias == 'APERTURE1':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_Aperture
        elif alias == 'JPEGSIZE':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_ImageSize
        elif alias == 'FILE_TYPE':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_CompressionLevel
        elif alias == 'EXPMODE':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_ExposureMode
        elif alias == 'NOISERED':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_NoiseReduction 
        elif alias == 'LOCKFOCUS':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_AEAFLockButton2CapAreaCrop
        elif alias == 'ISOINT':
            return Nikon.eNkMAIDCapability.kNkMAIDCapability_SensitivityInterval

    def lockFocus(self):
        self._device.SetBoolean(Nikon.eNkMAIDCapability.kNkMAIDCapability_LockCamera, True)
        if self._device.GetUnsigned(Nikon.eNkMAIDCapability.kNkMAIDCapability_FocusMode) == 1:
            if self._device.GetUnsigned(Nikon.eNkMAIDCapability.kNkMAIDCapability_AFMode) != 4:
                try:
                    self._device.SetBoolean(Nikon.eNkMAIDCapability.kNkMAIDCapability_LockCamera, True)
                    print 'Disabling AutoFocus' 
                    self._device.SetUnsigned(Nikon.eNkMAIDCapability.kNkMAIDCapability_AFMode, long('4'))
                    print 'AutoFocus Sucessfully Disabled'
                except Nikon.NikonException, ex:
                    print ex.Message
                    print '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'
                    print 'AutoFocus disable failed!'
                    print 'Please try to use digicamcontrol to disable autofocus and rerun NikEpics'
                    pass
        else:
            print 'Manual focus switch/switches on, Motorized focus not possible'

#   Get the camera name. This will be the PV prefix    
    def getDeviceName(self):
        return self._device.GetString(Nikon.eNkMAIDCapability.kNkMAIDCapability_Name)
#   currently unused 
    def getBattery(self):
        return self._device.GetInteger(Nikon.eNkMAIDCapability.kNkMAIDCapability_BatteryLevel)
#   get the focus setting.  
    def getFocusMode(self):
        return self._device.GetUnsigned(Nikon.eNkMAIDCapability.kNkMAIDCapability_AFMode)  
        
    def getLensInfo(self):
        return self._device.GetString(Nikon.eNkMAIDCapability.kNkMAIDCapability_LensInfo)      
        
    def getBit(self):
        return self._device.GetUnsigned(Nikon.eNkMAIDCapability.kNkMAIDCapability_CompressRAWBitMode)
        
    def setBit(self,value):
        self._device.SetUnsigned(Nikon.eNkMAIDCapability.kNkMAIDCapability_CompressRAWBitMode, long(value))
    
    def setCompress(self,value):
        self._device.SetUnsigned(Nikon.eNkMAIDCapability.kNkMAIDCapability_CompressRAWEx, long(value))

    def setenum(self, alias, value):
        name = self.getcapname(alias)
        try:
            e = self._device.GetEnum(name)
            e.Index = value
            self._device.SetEnum(name, e)
        except Nikon.NikonException as ex:
            print ex.Message

    def getenum(self, alias):
        return self._device.GetEnum(self.getcapname(alias))
        
    def getenumstring(self, alias):
        return str(self._device.GetEnum(self.getcapname(alias)))
        
    def getenumlist(self, alias):
        e = self._device.GetEnum(self.getcapname(alias))
        enumlist=[]
        for x in range(e.Length):
            enumlist.append(str(e.GetEnumValueByIndex(x)))
        #if len(enumlist) > 16:
        #    chunks=[enumlist[x:x+16] for x in xrange(0, len(enumlist), 16)]
        #    return chunks
        return enumlist
    
    def getenumindex(self, alias):
        return self._device.GetEnum(self.getcapname(alias)).Index

    def getboolean(self,alias):
        return self._device.GetBoolean(self.getcapname(alias))
        
    def setboolean(self,alias):
        name=self.getcapname(alias)
        e = self._device.GetBoolean(name)
        print e
        self._device.SetBoolean(name,'True')

    def connect(self):
        try:
            self._waitForDevice.wait()
            #self._device.CaptureComplete += self._device_CaptureComplete
        except Nikon.NikonException as ex:
            print ex.Message 

    def startlv(self):
        self._device.LiveViewEnabled = 1

    def stoplv(self):
        self._device.LiveViewEnabled = 0

    def getLV(self):
        return self._device.GetLiveViewImage()

    def cap(self):
        try:
            self._device.ImageReady +=  Nikon.ImageReadyDelegate(self.deviceImageReady)  
            self._device.Capture()
            self._waitForCapture.wait()
        except Nikon.NikonException, ex:
            print ex.Message
            pass

    def deviceImageReady(self, sender, image):
        self._waitForCapture.set()
        
    def bulbcapstart(self):
        try:
            self._device.StartBulbCapture()
        except Nikon.NikonException as ex:
            print ex.Message 
            pass

    def bulbcapstop(self):
        try:
            self._device.StopBulbCapture()
        except Nikon.NikonException as ex:
            print ex.Message
            pass
        #self._waitForCapture.wait()

    def manager_DeviceAdded(self, sender, device):
#       Save Nikon device object
        try:
            self._device = device
            self._waitForDevice.set()
        except Nikon.NikonException as ex:
            print ex.Message

    def manager_DeviceRemoved(self, sender, device):
        self._device = None

    def Exit(self):
        self.manager.Shutdown()
        self.manager = None
        
#   helper function to display device capabilities        
    def getAllCaps(self):
        self.allCaps = self._device.GetCapabilityInfo()
        for caps in self.allCaps:
            print("ID:%s\tType:%s" % (caps.ulID, caps.ulType))
        
