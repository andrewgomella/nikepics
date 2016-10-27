import numpy as np
import os
from PIL import Image
from smc.freeimage import Image as fimage


"""
Simple conversion of Nikon raw NEF files called via file location. 
supports selection of green color channel only, standard binning, cropping,
saves as tif to specified location, optionally deleting original NEF file
 
Designed with specific intent to be called from Nikon DSLR Epics driver.
Will also work with other python scripts (useful for testing without camera)

Dependecies:
    smc.freeimage 0.3dev:
        https://pypi.python.org/pypi/smc.freeimage
        install with "pip install smc.freeimage"
        may need to fix file hierarchy and manually copy egg file into site-packages
        after installing, site-packages directory should contain:
            .PTH file named something like " smc.freeimage-0.3dev-py2.7-nspkg.pth " 
            smc folder with freeimage folder within

    64bit version of FreeImage.dll:
        https://sourceforge.net/projects/freeimage/?source=typ_redirect
        download the 64bit version of the dll and then overwrite the included FreeImage.dll
        at the time of writing:
            smc.freeimage bundled DLL: 3.15.3.0
            downloaded FreeImage 64bit DLL: 3.17.0.0 

History/Notes:
    Past versions allowed direct transfer of the image buffer, rather than
    saving to disk and reading it back out. However direct transfer proved to 
    be difficult due to memory leaks (occuring after several hundred images, causing scans to fail)
    and did not cause that much benefit in speed vs saving and reading back from disk.
    It is also a more difficult feature to implement. Saving to disk first has proven
    to generally be the superior option especially when an SSD is being used. It also
    has the benefit of effectively backing up the NEF since it is saved first. After conversion
    to tiff is complete the option to delete the original NEF is available.
 
    Many methods are available to convert nef to tiff, but few are up to date and offer
    all of the features needed. There are also not many that work well with python, as most
    are in C or Cpp.
    
    The current method uses the FreeImage library (which is a widely used popular image processing library based 
    in C++). http://freeimage.sourceforge.net/ It uses libraw behind the scenes for processing raw images. 
    http://www.libraw.org/ . There is no official python distribution, however there is a version online 
    which works well even though it is not updated often. That is "smc.freeimage." 
    https://github.com/SemanticsOS/smc.freeimage 
    The calls to get the raw data are fairly simple. Just need to load the image into freeimage and specify
    the RAW_UNPROCESSED flag. 

    The current method allows conversion of an uncompressed D800 Nikon NEF file to 16 bit tiff in 0.25 seconds
    on an i7 3820 processor. 

    Another method uses rawkit which is available on github/pypi and so far appears to be well
    supported and offer the features we need. It also works via libraw, which I compiled for 64bit dll and 
    will package with this code. Main issue with rawkit is that it is very slow, resulting in 10 seconds
    of processing time to get raw data. It is also focused on linux, but works well with windows with 
    slight modificiation. 
    
    The oldest method also used libraw.dll, however with a manual implementation with ctypes 
    which was coded inhouse. Due to infamiliarity with ctypes this was a fairly cumbersome way
    to handle it. The newer rawkit (in use now) also is the same method but coded by others into
    a much more thorough library, rather than a quick implementation of ctypes. 


Andrew Gomella, 7/2016 (original work throughout 2014-2015)
Imaging Physics Lab, NHLBI, NIH
"""
class neftotiff():
    def __init__(self):
        self.height = 0
        self.width = 0
        self.numimages = 0

    def bufferToNumpyArray(self, image):
        t1=time.clock()
        try:
            #load image into freeimage module with flags=8, correspoding to UNPROCESSED_RAW
            x=fimage(image, flags=8)
            #store image width and height in class variables
            self.width=x.width
            self.height=x.height
            x=x.flipVertical()
            a= np.frombuffer(x.getRaw(), np.uint16)
        except Exception as e:
            print "Neftotiff failed during buffertonumpyarray function"
            print "num images:", self.numimages
            print "error:", e
        return a

    def ntt(self, image, nefwritename, savenef, name, y, x, y0, x0, binning, green):
        try:
            if y=='':
                y=0
            if x=='':
                x=0
            if y0=='':
                y0=0
            if x0=='':
                x0=0
            a=self.bufferToNumpyArray(image)#use function from neftotiff class to convert raw buffer to raw numpy array
            a.setflags(write=True)
            a.shape=(self.height,self.width) #a is still one long array, reshape to be height * width
            
            if green ==1:
                a=a[::2,1::2]+a[1::2,::2]#green pixels only
            else:
                a=a[1::2,1::2]+a[::2,::2]+a[::2,1::2]+a[1::2,::2]

            a = a.astype(np.uint32) #so calculations will perform correctly

            if a.shape[0]%binning !=0:
                #crop array 
                nn=round(a.shape[0]//binning)*binning #new array dimension
                mm=a.shape[0]-nn
                a=a[:-mm,:]
            if a.shape[1]%binning !=0:
                #crop array
                nn=round(a.shape[1]//binning)*binning #new array dimension
                mm=a.shape[1]-nn
                a=a[:,:-mm]
            a=a.reshape(a.shape[0]//binning,binning,a.shape[1]//binning,binning).mean(axis=(1,3))    

            #convert numpy array into PIL image object
            im = Image.fromarray(a)
            
            #crop if necessary
            if y != 0 != x != 0:
                im=im.crop((x0,y0,x0+x,y0+y))

            #save the tiff file
            im.save(name + '.tif')

            im= None
            self.numimages+=1
            if savenef == 0:
                os.remove(nefwritename)

        except Exception as e:
            print "nef to tiff failed after", self.numimages, "images."
            print "the error that caused this is:", e
            self.numimages=0
            return 1

