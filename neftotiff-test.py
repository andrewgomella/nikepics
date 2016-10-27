import neftotiff
#simple offline test of nef to tiff conversion 

InputImage= 'test.nef'
saveNefFilename='test-NEF.nef'
saveTifFilename='test-Tif.tif'
saveNef=1

#Cropping coordinates
y=0
x=0
y0=0
x0=0

binning=1
green=0

if __name__ == '__main__':
	#initialize nef to tiff class 
	imgconvert = neftotiff.neftotiff()
	imgconvert.ntt(InputImage, saveNefFilename, saveNef, saveTifFilename, y, x, y0, x0, binning, green)
