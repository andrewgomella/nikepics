**NikEpics v2**
===============
Andrew Gomella and Alireza Panna 

**Version 2.0:**
----------------
* Updated to work with x64 python
* PV back up and restore now done using epics.autosave

**Version 1.1:**
----------------
* 4/06/15: Added devIocStats record supports 
* 4/06/15: Added capability to run ioc as daemon using procServ (http://sourceforge.net/projects/procserv/)
* 4/06/15: Added some records from nikoncswrapper (ported from v2.0 beta)
* 4/06/15: Added a record to scan focus mode every 30s
* 4/06/15: nikonqt screen updated to implement some of these new record. Renamed as nikonqt-v1.2
* 4/21/15: Added sync support for oxford series micro focus x-ray source. Updated qt screen as well

**Version 1.0:**
----------------
* 10/01/2013: First version created

**Known Bugs:**
---------------
1. When first boot red x shows on client caqt screen up even if file exists
2. The win32serviceutil library throws an error when used with procServ

**To-do:**
----------
1. neftotiff needs stress testing with live scans
2. add rotation option to neftotiff
3. add documentation (how to get set up)
4. cpi sync functionality