# HDHR Viewer V2 v0.9.0

import time
import string
from datetime import datetime
import urllib
import os
from lxml import etree

TITLE                = 'HDHR Viewer 2 (0.9)'
PREFIX               = '/video/hdhrv2'
VERSION              = '0.9.0'

#GRAPHICS
ART                  = 'art-default.jpg'
ICON                 = 'icon-default.png'
ICON_SUBBED_LIST     = 'icon-subscribed.png'
ICON_FAV_LIST        = 'icon-fav.png'
ICON_DEFAULT_CHANNEL = 'icon-subscribed.png'
ICON_SETTINGS        = 'icon-settings.png'
ICON_ERROR           = 'icon-error.png'
ICON_UNKNOWN         = 'icon-unknown.png'

#PREFS
PREFS_HDHR_IP        = 'hdhomerun_ip'
PREFS_HDHR_TUNER     = 'hdhomerun_tuner'
PREFS_XMLTV_MODE     = 'xmltv_mode'
PREFS_XMLTV_FILE     = 'xmltv_file'
PREFS_LOGO_MATCH     = 'channellogo'
PREFS_XMLTV_MATCH    = 'xmltv_match'

#XMLTV Modes
XMLTV_MODE_RESTAPI   = 'restapi'
XMLTV_MODE_HDHOMERUN = 'hdhomerun'
XMLTV_MODE_FILE      = 'file'

#DATE/TIME FORMATS
TIME_FORMAT          = '%H:%M'
DATE_FORMAT          = '%Y%m%d'

#HDHOMERUN GUIDE URL
URL_HDHR_DISCOVER         = 'http://{ip}/discover.json'
URL_HDHR_DISCOVER_DEVICES = 'http://192.168.1.11/discover' #dev
#URL_HDHR_DISCOVER_DEVICES = 'http://my.hdhomerun.com/discover'
URL_HDHR_GUIDE            = 'http://my.hdhomerun.com/api/guide.php?DeviceAuth={deviceAuth}'
#URL_HDHR_GUIDE            = 'http://127.0.0.1/guide.php?DeviceAuth={deviceAuth}'
URL_HDHR_LINEUP           = 'http://{ip}/lineup.json'
URL_HDHR_STREAM           = 'http://{ip}:5004/{tuner}/v{guideNumber}'
CACHETIME_HDHR_GUIDE      = 3600 # (s) Default: 3600 = 1 hour

#CONSTANTS/PARAMETERS
TIMEOUT = 5                 # XML Timeout (s); Default = 5
TIMEOUT_LAN = 1             # LAN Timeout (s)
CACHETIME = 5               # Cache Time (s); Default = 5
MAX_FAVORITES = 10          # Max number of favorites supported; Default = 10
VIDEO_DURATION = 14400000   # Duration for Transcoder (ms); Default = 14400000 (4 hours)
MAX_SIZE = 90971520         # [Bytes] 20971520 = 20MB; Default: 90971520 (100MB)


###################################################################################################
# Entry point - set up default values for all containers
###################################################################################################
def Start():
    
    ObjectContainer.title1 = TITLE
    ObjectContainer.art = R(ART)

    DirectoryObject.thumb = R(ICON)
    DirectoryObject.art = R(ART)
    HTTP.CacheTime = CACHETIME
    

###################################################################################################
# Main Menu
###################################################################################################
@handler(PREFIX, TITLE, art=ART, thumb=ICON)
def MainMenu():

    global HDHRV2
    HDHRV2 = Devices()
    GetInfo()
    
    oc = ObjectContainer(no_cache=True)

    # Only show favorites or tuners if tuners are found    
    if len(HDHRV2.tunerDevices)>0:
        # add any enabled favorites
        favoritesList = LoadEnabledFavorites()
        for favorite in favoritesList: 
            ocTitle = favorite.name+' ('+xstr(favorite.totalChannels)+')'
            oc.add(DirectoryObject(key=Callback(FavoriteChannelsMenu, index=favorite.index), title=ocTitle, thumb=R(ICON_FAV_LIST)))

        # Multi Tuner support
        for tuner in HDHRV2.tunerDevices:
            strTuner = JSON.StringFromObject(tuner)
            ocTitle = tuner['LocalIP']+' ('+xstr(getLineupDetails(tuner,'TotalChannels'))+')'
            # Identify Manual Tuners
            if tuner['autoDiscover']==False:
                ocTitle='M:'+ocTitle
            oc.add(DirectoryObject(key=Callback(AllChannelsMenu, tuner=strTuner), title=ocTitle, thumb=R(ICON_SUBBED_LIST)))

    # If No Tuners were found
    else:
        ocTitle = 'No Tuners Found'
        oc.add(DirectoryObject(title=ocTitle, thumb=R(ICON_ERROR)))

    # Search programs playing now / Not tested in 0.9
    if isXmlTvModeRestApi():
        oc.add(InputDirectoryObject(key=Callback(SearchResultsChannelsMenu), title='Search Playing Now', thumb=R(ICON_SUBBED_LIST)))

    # Settings Menu
    oc.add(PrefsObject(title='Settings', thumb=R(ICON_SETTINGS)))

    return oc

    
###################################################################################################
# This function produces a directory for all channels the user is subscribed to
###################################################################################################
@route(PREFIX + '/all-channels')
def AllChannelsMenu(tuner):
    try:
        tuner=JSON.ObjectFromString(tuner)
        allChannels = LoadAllChannels(tuner)
        PopulateProgramInfo(tuner, allChannels.list, False)
        return BuildChannelObjectContainer(tuner,tuner['LocalIP'], allChannels.list)

    except Exception as inst:
        logError('AllChannelsMenu(tuner)',inst)
        return BuildErrorObjectContainer(strError(inst))


###################################################################################################
# This function produces a directory for all channels the user is subscribed to
# Note, we only show program info for the favorites, because the full channel list can be a bit too
# large (well, for folks subscribing to cable)
###################################################################################################
@route(PREFIX + '/favorite-channels')
def FavoriteChannelsMenu(index):

    allChannels = []
    channelList = []
    selected_tuner = []
    tuner_index=0
    tuner_defined=False
    
    favorite = LoadFavorite(index)
    
    # If tuner IP is defined in Fav list, and exist in Tuner list
    for tuner in HDHRV2.tunerDevices:
        if tuner['LocalIP']==favorite.tuner:
            allChannels=LoadAllChannels(tuner)
            selected_tuner=tuner
            tuner_defined=True
            break
        tuner_index+=1
    
    # If tuner IP not defined in Fav list, assume primary tuner.
    if not tuner_defined:
        logDebug('Tuner not defined in favorite list. Using primary tuner')
        selected_tuner=HDHRV2.tunerDevices[0]
        allChannels=LoadAllChannels(selected_tuner)

    # Filter favorite list
    for channelNumber in favorite.channels:
        channel = allChannels.map.get(channelNumber)
        if (channel is not None):
            channelList.append(channel)

    # Populate the program info for all of the channels
    PopulateProgramInfo(selected_tuner, channelList, True)

    return BuildChannelObjectContainer(selected_tuner,favorite.name,channelList)

###################################################################################################
# Disabled functionality
# This function produces a directory for all channels whose programs match the specified query
# key words
###################################################################################################
@route(PREFIX + '/search-channels')
def SearchResultsChannelsMenu(query):

    allChannels = LoadAllChannels()

    # Execute the search, and return a map of channel display-names to program
    # load all programs into a map (from channel display name -> program)
    allProgramsMap = {}

    xmltvApiUrl = ConstructApiUrl(None,False,query)
    allProgramsMap = {}
    try:
        jsonChannelPrograms = JSON.ObjectFromURL(xmltvApiUrl)
        allProgramsMap = BuildChannelToProgramMapFromProgramJson(jsonChannelPrograms)
    except Exception as inst:
        Log.Error(type(inst) + ": " + xstr(inst.args) + ": " + xstr(inst))
        return

    # build the channel result set
    # basically for any channels that were in the resulting programs, try to match the channel numbers
    # from HDHR with the display names.
    channels = []
    for channel in allChannels.list:
        try:
            program = allProgramsMap[channel.number]
            channel.setProgramInfo(program)
            channels.append(channel)
        except KeyError:
            pass

    # now create the object container with all of the channels as video clip objects, and return
    return BuildChannelObjectContainer("Search: " + query,channels)


###################################################################################################
# Utility function to populate the channels, including the program info if enabled in preferences
###################################################################################################
def BuildChannelObjectContainer(tuner, title, channels):
    # Create the object container and then add in the VideoClipObjects
    oc = ObjectContainer(title2=title)

    # setup the VideoClipObjects from the channel list
    for channel in channels:
        program = channel.program
        oc.add(CreateVO(tuner=tuner, url=channel.streamUrl,title=GetVcoTitle(channel), year=GetVcoYear(program), tagline=GetVcoTagline(program), summary=GetVcoSummary(program), starRating=GetVcoStarRating(program), thumb=GetVcoIcon(channel,program), videoCodec=channel.videoCodec, audioCodec=channel.audioCodec))
    return oc

###################################################################################################
# Return error message
###################################################################################################
def BuildErrorObjectContainer(errormsg):
    oc = ObjectContainer(title2=errormsg)
    oc.add(DirectoryObject(title=errormsg,tagline=errormsg,summary=errormsg,thumb=ICON_ERROR))
    return oc

###################################################################################################
# This function populates the channel with XMLTV program info coming from the xmltv rest service
###################################################################################################
def PopulateProgramInfo(tuner, channels, partialQuery):

    allProgramsMap = {}

    #tempfix disable channelguide
    if iOSPlex44():
        return

    #xmltv hdhomerun
    if Prefs[PREFS_XMLTV_MODE] != 'disable':
        try:
            # If automatically discovered, force HDHomeRun guide.
            if tuner['autoDiscover']:
                xmltvApiUrl = getDeviceDetails(tuner,'GuideURL')
                jsonChannelPrograms = JSON.ObjectFromURL(xmltvApiUrl,cacheTime=CACHETIME_HDHR_GUIDE)
                allProgramsMap = ProgramMap_HDHomeRun(jsonChannelPrograms)

            # Manual Tuners, use Settings
            else:
                #HDHomeRun
                if Prefs[PREFS_XMLTV_MODE]==XMLTV_MODE_HDHOMERUN:
                    xmltvApiUrl = getDeviceDetails(tuner,'GuideURL')
                    jsonChannelPrograms = JSON.ObjectFromURL(xmltvApiUrl,cacheTime=CACHETIME_HDHR_GUIDE)
                    allProgramsMap = ProgramMap_HDHomeRun(jsonChannelPrograms)
                #RestAPI
                if Prefs[PREFS_XMLTV_MODE]==XMLTV_MODE_RESTAPI:
                    xmltvApiUrl = ConstructApiUrl(channels,partialQuery)
                    #Log.Debug("xmltvApiUrl:"+xmltvApiUrl)
                    jsonChannelPrograms = JSON.ObjectFromURL(xmltvApiUrl)
                    allProgramsMap = BuildChannelToProgramMapFromProgramJson(jsonChannelPrograms)
                #XMLTV    
                if Prefs[PREFS_XMLTV_MODE]==XMLTV_MODE_FILE:
                    channelList = []
                    try:
                        for channel in channels:
                            if Prefs[PREFS_XMLTV_MATCH] == 'name':
                                channelList.append(channel.name)
                            else:
                                channelList.append(channel.number)
                        allProgramsMap = ProgramMap_File(channelList)
                    except Exception as inst:
                        logError('XMLTV Mode Channel List',inst)
                        return

        except Exception as inst:
            Log.Error(xstr(type(inst)) + ": " + xstr(inst.args) + ": " + xstr(inst))
            return

    # go through all channels and set the program
    for channel in channels:
        try:
            if Prefs[PREFS_XMLTV_MATCH] == 'name':
                program = allProgramsMap[channel.name]
            else:
                program = allProgramsMap[channel.number]
            channel.setProgramInfo(program)
        except KeyError:
            pass

    return


###################################################################################################
# This function parses the given program json, and then builds a map from the channel display 
# name (all of them) to the Program object
###################################################################################################
def ProgramMap_RestAPI(jsonChannelPrograms):
    allProgramsMap = {}
    t = time.time()
    for jsonChannelProgram in jsonChannelPrograms:
        # parse the program and the next programs if they exist
        program = ParseProgramJson(XMLTV_MODE_RESTAPI,jsonChannelProgram["program"])
        jsonNextPrograms = jsonChannelProgram["nextPrograms"]
        if jsonNextPrograms is not None:
            for jsonNextProgram in jsonNextPrograms:
                program.next.append(ParseProgramJson(XMLTV_MODE_RESTAPI,jsonNextProgram))
                
        # now associate all channel display names with that same program object
        jsonChannelDisplayNames = jsonChannelProgram["channel"]["displayNames"]
        for displayName in jsonChannelDisplayNames:
            allProgramsMap[displayName] = program

    logDebug("Time taken to parse RestAPI JSON: "+str(time.time()-t))
            
    return allProgramsMap

def ProgramMap_HDHomeRun(jsonChannelPrograms):
    allProgramsMap = {}
    t = time.time()
    for jsonChannelProgram in jsonChannelPrograms:
        # parse the program and the next programs if they exist
        totalPrograms = len(jsonChannelProgram["Guide"])
        program = ParseProgramJson(XMLTV_MODE_HDHOMERUN,jsonChannelProgram["Guide"][0])
        i=0
        while (program.stopTime < time.time() and i<totalPrograms):
            program = ParseProgramJson(XMLTV_MODE_HDHOMERUN,jsonChannelProgram["Guide"][i])
            i=i+1
        jsonNextPrograms = jsonChannelProgram["Guide"][i:min(int(Prefs["xmltv_show_next_programs_count"])+i,totalPrograms)]
        if jsonNextPrograms is not None:
            for jsonNextProgram in jsonNextPrograms:
                program.next.append(ParseProgramJson(XMLTV_MODE_HDHOMERUN,jsonNextProgram))
        if program.icon=="":
            program.icon=jsonChannelProgram.get("ImageURL","")
        jsonChannelDisplayNames = jsonChannelProgram.get("GuideNumber")
        allProgramsMap[jsonChannelDisplayNames] = program

    logDebug("Time taken to parse HDHOmeRun JSON: "+str(time.time()-t))
            
    return allProgramsMap

def ProgramMap_File(channellist):

    t = time.time()    
    allProgramsMap = {}

    channels = []
    channelIDs = []

    channelID = None
    channelNumber = None
    c_channelID = None
    p_channelID = None
    program=None
    i=0
    
    for event, elem in etree.iterparse(Prefs[PREFS_XMLTV_FILE],events=("start", "end")):
        # get channelIDs that are requested.
        if elem.tag == 'channel' and event=='start':
            channelID = elem.attrib.get('id')
            for dispname in elem.findall('display-name'):
                if dispname.text in channellist:
                    channels.append(dispname.text)
                    channelIDs.append(channelID)
            elem.clear()
        
        # get programs
        if elem.tag == 'programme' and event=='start' and len(channelIDs)>0:
                
            currTime = int(datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S'))
            stopTime = int(elem.attrib.get('stop')[:14])
            c_channelID = elem.attrib.get('channel')
            
            if currTime<stopTime and c_channelID==p_channelID and i<=int(Prefs["xmltv_show_next_programs_count"]) and c_channelID in channelIDs:
                channelindex = channelIDs.index(c_channelID)
                channelmap = channels[channelindex]
                stopTime = time.mktime(datetime.strptime(str(stopTime),'%Y%m%d%H%M%S').timetuple())
                startTime=int(elem.attrib.get('start')[:14])
                startTime=time.mktime(datetime.strptime(str(startTime),'%Y%m%d%H%M%S').timetuple())
                title=xstr(elem.findtext('title'))
                subTitle=xstr(elem.findtext('sub-title'))
                desc=xstr(elem.findtext('desc'))
                date=xstr(elem.findtext('date'))
                icon_e=elem.find('icon')
                icon=None
                if icon_e!=None:
                    icon=xstr(icon_e.attrib.get('src'))
                starRating=0.0
                
                if i==0:    
                    # current listing
                    program = Program(startTime,stopTime,title,date,subTitle,desc,icon,starRating)
                else:
                    #next listing
                    program.next.append(Program(startTime,stopTime,title,date,subTitle,desc,icon,starRating))
                    
                i+=1
                elem.clear()
            elif c_channelID!=p_channelID:
                if program!=None:
                    allProgramsMap[channelmap] = program
                i=0
                elem.clear()
            else:
                elem.clear()
            p_channelID=c_channelID
    
    logDebug("Time taken to parse XMLTV: "+str(time.time()-t))

    return allProgramsMap
    
###################################################################################################
# This function returns whether the xmltv_mode is set to restapi or hdhomerun
###################################################################################################
def isXmlTvModeRestApi():
    xmltv_mode = xstr(Prefs[PREFS_XMLTV_MODE])
    return (xmltv_mode == XMLTV_MODE_RESTAPI)
    
def isXmlTvModeHDHomeRun():
    xmltv_mode = xstr(Prefs[PREFS_XMLTV_MODE])
    return (xmltv_mode == XMLTV_MODE_HDHOMERUN) 

def isXmlTvModeFile():
    xmltv_mode = xstr(Prefs[PREFS_XMLTV_MODE])
    return (xmltv_mode == XMLTV_MODE_FILE)         

###################################################################################################
# This function constructs the url with query to obtain the currently playing programs
###################################################################################################
def ConstructApiUrl(channels, partialQuery, filterText = None):
    xmltvApiUrl = Prefs["xmltv_api_url"]
    showNextProgramsCount = int(Prefs["xmltv_show_next_programs_count"])

    # construct the parameter map, and then use the url encode function to ensure we are compliant with the spec
    paramMap = {}
    paramMap["show_next"] = str(showNextProgramsCount)
    if filterText is not None:
        paramMap["filter_text"] = filterText
    
    # if partialQuery, then we want to include a channels parameter with the csv of the channel numbers
    if partialQuery:
        if Prefs[PREFS_XMLTV_MATCH] == "name":
            csv = ",".join([channel.name for channel in channels])
        else:
            csv = ",".join([channel.number for channel in channels])
        paramMap["channels"] = csv
        
    xmltvApiUrl += "?" + urllib.urlencode(paramMap)
    return xmltvApiUrl
                        
###################################################################################################
# This function parses a Program json object
###################################################################################################
def ParseProgramJson(mode,jsonProgram):
    #isXmlTvModeRestApi
    if mode==XMLTV_MODE_RESTAPI:
        startTime = int(jsonProgram.get('start'))/1000
        stopTime = int(jsonProgram.get('stop'))/1000
        title = xstr(jsonProgram.get('title',''))
        date = xstr(jsonProgram.get('date',0))
        subTitle = xstr(jsonProgram.get('subtitle',''))
        desc = xstr(jsonProgram.get('desc',''))
        starRating = xstr(jsonProgram.get('starRating',''))
        icon = xstr(jsonProgram.get('icon',''))
    else:
        startTime = int(jsonProgram.get('StartTime'))
        stopTime = int(jsonProgram.get('EndTime'))
        title = xstr(jsonProgram.get('Title'))
        date = GetDateDisplay(jsonProgram.get('OriginalAirdate',0))
        subTitle = xstr(jsonProgram.get('Affiliate',''))
        desc = xstr(jsonProgram.get('Synopsis',''))
        starRating = xstr('')
        icon = xstr(jsonProgram.get('ImageURL',''))
    return Program(startTime,stopTime,title,date,subTitle,desc,icon,starRating)

###################################################################################################
# This function returns the title to be used with the VideoClipObject
###################################################################################################
def GetVcoTitle(channel):
    title = xstr(channel.number) + " - " + xstr(channel.name)

    #tempfix for iOS Plex 4.4
    if iOSPlex44():
        title = title.replace(" ","")
	
    if (channel.hasProgramInfo() and channel.program.title is not None):
        title += ": " + channel.program.title
    return title
    
###################################################################################################
# This function returns the tagline to be used with the VideoClipObject
###################################################################################################
def GetVcoTagline(program):
    tagline = ""
    if (program is not None):
        startTimeDisplay = GetTimeDisplay(program.startTime)
        stopTimeDisplay = GetTimeDisplay(program.stopTime)
        tagline = startTimeDisplay + " - " + stopTimeDisplay + ": " + xstr(program.title)
        if (program.subTitle):
            tagline += " - " + program.subTitle
    return tagline

###################################################################################################
# This function returns the summary to be used with the VideoClipObject
###################################################################################################
def GetVcoSummary(program):
    summary = ""
    if (program is not None):
        if (program.desc is not None):
            summary += program.desc
        if (len(program.next) > 0):
            summary += "\nNext:\n"
            for nextProgram in program.next:
                summary += GetVcoTagline(nextProgram) + "\n"
    return summary

###################################################################################################
# This function returns the star rating (float value) for the given progam
###################################################################################################
def GetVcoStarRating(program):
    starRating = 0.0
    if (program is not None):
        if (program.starRating is not None):
            try:
                textArray = program.starRating.split("/")
                numerator = float(textArray[0])
                denominator = float(textArray[1])
                starRating = float(10.0*numerator / denominator)
            except:
                starRating = 0.0
    return starRating

###################################################################################################
# This function returns the star rating (float value) for the given progam
###################################################################################################
def GetVcoYear(program):
    year = None
    if (program is not None and program.date is not None):
        year = program.date
    return year

###################################################################################################
# This function returns the icon for the given progam
###################################################################################################	
def GetVcoIcon(channel,program):
    # Create safe names
    icon_channelname = makeSafeFilename(channel.name)+'.png'
    icon_channelnumber = makeSafeFilename(channel.number)+'.png'

    # If program or channel doesn't have icon, try name then name (new name old names)
    if (program is not None and program.icon is not None):
        if program.icon != "":
            icon = program.icon
    elif Core.storage.resource_exists(icon_channelname):
        icon = R(icon_channelname)
    elif Core.storage.resource_exists('logo-'+icon_channelname):
        icon = R('logo-'+icon_channelname)
    elif Core.storage.resource_exists(icon_channelnumber):
        icon = R(icon_channelnumber)
    elif Core.storage.resource_exists('logo-'+icon_channelnumber):
        icon = R('logo-'+icon_channelnumber)
    else:
        icon = R(ICON_UNKNOWN)
    return icon
    
###################################################################################################
# This function converts a time in milliseconds to a time text
###################################################################################################
def GetTimeDisplay(timeInMs):
    timeInSeconds = timeInMs
    return datetime.fromtimestamp(timeInSeconds).strftime(TIME_FORMAT)
    
###################################################################################################
# This function converts a time in milliseconds to a time text
###################################################################################################
def GetDateDisplay(timeInSeconds):
    if timeInSeconds==0:
        return ""
    return datetime.fromtimestamp(timeInSeconds).strftime(DATE_FORMAT)
    
    
###################################################################################################
# This function loads the list of all enabled favorites
###################################################################################################
def LoadEnabledFavorites():
    favorites = []
    for i in range(1,MAX_FAVORITES+1):
        favorite = LoadFavorite(i)
        if (favorite.enable):
            favorites.append(favorite)
    return favorites

###################################################################################################
# This function loads the favorite identified by the index i
###################################################################################################
def LoadFavorite(i):
    enable = Prefs['favorites.' + str(i) + '.enable']
    name   = Prefs['favorites.' + str(i) + '.name']
    list   = Prefs['favorites.' + str(i) + '.list']
    sortBy = Prefs['favorites.' + str(i) + '.sortby']
    return Favorite(i,enable,name,list, sortBy)

###################################################################################################
# This function loads the full channel list from the configured hdhrviewer host
###################################################################################################
## Multi Tuner Support
def LoadAllChannels(tuner):
    allChannelsList = []
    allChannelsMap = {}

    jsonLineupUrl = tuner['LineupURL']
    jsonLineup = JSON.ObjectFromURL(jsonLineupUrl,timeout=TIMEOUT_LAN)

    for channel in jsonLineup:
        guideNumber = channel.get('GuideNumber')
        guideName = channel.get('GuideName','')
        videoCodec = channel.get('VideoCodec','')
        audioCodec = channel.get('AudioCodec','')
        streamUrl = channel.get('URL','')

        channelLogo = ICON_DEFAULT_CHANNEL

        channel = Channel(guideNumber,guideName,streamUrl,channelLogo,videoCodec,audioCodec)
        allChannelsList.append(channel)
        allChannelsMap[guideNumber] = channel

    allChannels = ChannelCollection(allChannelsList,allChannelsMap)
    return allChannels

###################################################################################################
# Get HDHomeRun Device details
###################################################################################################
def getDeviceDetails(tuner,detail):
    try:
        deviceDetails = ''
        jsonDiscoverUrl = tuner['DiscoverURL']
        jsonDiscover = JSON.ObjectFromURL(jsonDiscoverUrl,timeout=TIMEOUT_LAN)

        deviceAuth = jsonDiscover.get('DeviceAuth')

        if detail=='GuideURL' and deviceAuth is not None:
            deviceDetails = URL_HDHR_GUIDE.format(deviceAuth=deviceAuth)
            logDebug(deviceDetails)
        else:
            deviceDetails = jsonDiscover.get(detail,'')
    except Exception as inst:
        logError('getDeviceDetails()',inst)
    return deviceDetails

###################################################################################################
# Get HDHomeRun Lineup details
###################################################################################################

def getLineupDetails(tuner,detail):
    try:
        lineupDetails = None
        jsonDiscoverUrl = tuner['LineupURL']
        jsonDiscover = JSON.ObjectFromURL(jsonDiscoverUrl,timeout=TIMEOUT_LAN)

        if detail=='TotalChannels':
            lineupDetails = len(jsonDiscover)
        else:
            lineupDetails = 0
    except Exception as inst:
        logError('getLineupDetails()',inst)
    return lineupDetails

###################################################################################################
# This function is taken straight (well, almost) from the HDHRViewer V1 codebase
###################################################################################################
@route(PREFIX + "/CreateVO")
def CreateVO(tuner, url, title, year=None, tagline="", summary="", thumb=R(ICON_DEFAULT_CHANNEL), starRating=0, include_container=False, checkFiles=0, videoCodec='mpeg2video',audioCodec='AC3'):
    modelNumber = getDeviceDetails(tuner,'ModelNumber')
    
    # Allow trancoding only on HDTC-2US
    if modelNumber=="HDTC-2US":
        transcode = Prefs["transcode"]
    else:
        transcode = "default"

    if videoCodec=='MPEG2':
        videoCodec='mpeg2video'

    if transcode=='auto':
        videoCodec = VideoCodec.H264
        audioCodec = 'AC3'
        #AUTO TRANSCODE
        vo = VideoClipObject(
            rating_key = url,
            key = Callback(CreateVO, tuner=tuner, url=url, title=title, year=year, tagline=tagline, summary=summary, thumb=thumb, starRating=starRating, include_container=True, checkFiles=checkFiles, videoCodec=videoCodec,audioCodec=audioCodec),
            rating = float(starRating),
            title = xstr(title),
            year = xint(year),
            summary = xstr(summary),
            #Plex.tv & Roku3
            tagline = xstr(tagline),
            source_title = xstr(tagline),
            #without duration, transcoding will not work... 
            duration = VIDEO_DURATION,
            thumb = thumb,
            items = [   
                MediaObject(
                    parts = [PartObject(key=(url+"?transcode=heavy"))],
                    container = "mpegts",
                    video_resolution = 1080,
                    bitrate = 8000,
                    video_codec = videoCodec,
                    audio_codec = audioCodec,
                    audio_channels = 6,
                    optimized_for_streaming = True
                ),
                MediaObject(
                    parts = [PartObject(key=(url+"?transcode=mobile"))],
                    container = "mpegts",
                    video_resolution = 720,
                    bitrate = 2000,
                    video_codec = videoCodec,
                    audio_codec = audioCodec,
                    audio_channels = 6,
                    optimized_for_streaming = True
                ),
                MediaObject(
                    parts = [PartObject(key=(url+"?transcode=internet480"))],
                    container = "mpegts",
                    video_resolution = 480,
                    bitrate = 1500,
                    video_codec = videoCodec,
                    audio_codec = audioCodec,
                    audio_channels = 6,
                    optimized_for_streaming = True
                ),
                MediaObject(
                    parts = [PartObject(key=(url+"?transcode=internet240"))],
                    container = "mpegts",
                    video_resolution = 240,
                    bitrate = 720,
                    video_codec = videoCodec,
                    audio_codec = audioCodec,
                    audio_channels = 6,
                    optimized_for_streaming = True
                ),
            ]
        )
    elif transcode=="default":
        vo = VideoClipObject(
            rating_key = url,
            key = Callback(CreateVO, tuner=tuner, url=url, title=title, year=year, tagline=tagline, summary=summary, thumb=thumb, starRating=starRating, include_container=True, checkFiles=checkFiles, videoCodec=videoCodec, audioCodec=audioCodec),
            rating = float(starRating),
            title = xstr(title),
            year = xint(year),
            summary = xstr(summary),
            #Plex.tv & Roku3
            tagline = xstr(tagline),
            source_title = xstr(tagline),
            duration = VIDEO_DURATION,
            thumb = thumb,
            items = [   
                MediaObject(
                    parts = [PartObject(key=(url))],
                    container = "mpegts",
                    video_resolution = 1080,
                    bitrate = 20000,
                    video_codec = videoCodec,
                    audio_codec = audioCodec,
                    audio_channels = 6,
                    optimized_for_streaming = True
                )
            ]   
        )
    else:
        #Log.Debug(url+"?transcode="+transcode)
        if transcode!='none':
            videoCodec = VideoCodec.H264
	    audioCodec = 'AC3'
        vo = VideoClipObject(
            rating_key = url,
            key = Callback(CreateVO, tuner=tuner, url=url, title=title, year=year, tagline=tagline, summary=summary, thumb=thumb, starRating=starRating, include_container=True, checkFiles=checkFiles, videoCodec=videoCodec, audioCodec=audioCodec),
            rating = float(starRating),
            title = xstr(title),
            year = xint(year),
            summary = xstr(summary),
            #Plex.tv & Roku3
            tagline = xstr(tagline),
            source_title = xstr(tagline),
            #without duration, transcoding will not work... 
            duration = VIDEO_DURATION,
            thumb = thumb,
            items = [   
                MediaObject(
                    parts = [PartObject(key=(url+"?transcode="+Prefs["transcode"]))],
                    container = "mpegts",
                    video_codec = videoCodec,
                    audio_codec = audioCodec,
                    audio_channels = 6,
                    optimized_for_streaming = True
                )
            ]   
        )

    if include_container:
        return ObjectContainer(objects=[vo])
    else:
        return vo

###################################################################################################
# Utility to convert an object to a string (and mainly handle the NoneType case)
# Credit: from a stackoverflow article
###################################################################################################
def xstr(s):
    if s is None:
        return ' '
    else:
        return str(s)        

###################################################################################################
# Utility to convert an object to an integer (and handle the NoneType case)
###################################################################################################
def xint(s):
    if (s is None or len(s)==0):
        return None
    else:
        try:
            return int(s)
        except:
            return None
            
###################################################################################################
# Make safe file name for channel logo
###################################################################################################
def makeSafeFilename(inputFilename):     
    try:
        safechars = string.letters + string.digits + "-_."
        return filter(lambda c: c in safechars, inputFilename)
    except:
        return ""

###################################################################################################
# Check if resource exist
###################################################################################################
        
def resourceExist(inputFilename):
	return core.resource_exists(inputFilename)

###################################################################################################
# python 'any' function
###################################################################################################
    
def xany(iterable):
    for element in iterable:
        if element:
            return True
    return False

###################################################################################################
# logging / debuggung functions
###################################################################################################

def strError(inst):
    return xstr(type(inst)) + ": " + xstr(inst.args) + ": " + xstr(inst)

def logError(function,inst):
    Log.Error(function + strError(inst))

def logDebug(str):
    Log.Debug(xstr(str))

###################################################################################################
# Plex 4.4 for iOS detection
###################################################################################################   
def iOSPlex44():
    if Client.Product=="Plex for iOS" and Client.Version == "4.4":
        return True
    else:
        return False
		
###################################################################################################
# Client Information.
###################################################################################################				
def GetInfo():
    Log.Debug("PMS CPU            : "+Platform.CPU)
    Log.Debug("PMS OS             : "+Platform.OS)
    Log.Debug("PMS OS Version     : "+Platform.OSVersion)
    Log.Debug("PMS Version        : "+Platform.ServerVersion)
    Log.Debug("Client Platform    : "+Client.Platform)
    Log.Debug("Client Product     : "+Client.Product)
    Log.Debug("Client Version     : "+Client.Version)
    Log.Debug("HDHRV2 Version     : "+VERSION)
    Log.Debug("AppSupportPath     : "+Core.app_support_path)
    Log.Debug("PlugInBundle       : "+Core.storage.join_path(Core.app_support_path, Core.config.bundles_dir_name))
    Log.Debug("PluginSupportFiles : "+Core.storage.join_path(Core.app_support_path, Core.config.plugin_support_dir_name))

###################################################################################################
# MultiTuner + Auto Discovery + Manual IP
###################################################################################################		
class Devices:
    def __init__(self):
        self.storageServers = []
        self.tunerDevices = []
        self.manualTuner()
        self.autoDiscover(False)

    # Auto Discover devices
    def autoDiscover(self,rediscover):
        cacheTime=None
        if rediscover:
            cacheTime=CACHETIME_HDHR_GUIDE
        try:
            response = xstr(HTTP.Request(URL_HDHR_DISCOVER_DEVICES,timeout=TIMEOUT,cacheTime=cacheTime))
            JSONdevices = JSON.ObjectFromString(''.join(response.splitlines()))
            logDebug('Devices.autoDiscover(): '+xstr(len(JSONdevices))+' devices found')

            for device in JSONdevices:
                StorageURL = device.get('StorageURL')
                LineupURL = device.get('LineupURL')
                
                if LineupURL is not None:
                    if not xany(d['LocalIP']==device['LocalIP'] for d in self.tunerDevices):
                        device['autoDiscover'] = True
                        self.tunerDevices.append(device)
                    else:
                        # self.tunerDevices.append(device) #test
                        logDebug('Devices.autoDiscover(): Skipped '+device['LocalIP'])

                #future
                if StorageURL is not None:
                    self.storageServers.append(device)

        except Exception as inst:
            logError('Devices.autoDiscover()',inst)

    # Get manual tuners listed in Settings
    def manualTuner(self):
        try:
            manualTuners = Prefs[PREFS_HDHR_IP]
            if manualTuners is not None:
                # Only add tuners if not 'auto'
                if manualTuners != 'auto':
                    for tunerIP in manualTuners.split():
                        if not xany(d['LocalIP']==tunerIP for d in self.tunerDevices):
                            self.addManualTuner(tunerIP)
                        else:
                            # self.addManualTuner(tunerIP) #test
                            logDebug('Devices.manualIP(): Skipped '+tunerIP)
            else:
                logDebug('Devices.manualTuner(): No tuner to add')

        except Exception as inst:
            logError('Devices.manualTuner()',inst)

    # Add manual tuners
    def addManualTuner(self,tunerIP):
        try:
            tuner = {}
            tuner['autoDiscover'] = False
            tuner['DeviceID'] = 'Manual'
            tuner['LocalIP'] = tunerIP
            tuner['BaseURL'] = tunerIP
            tuner['DiscoverURL'] = URL_HDHR_DISCOVER.format(ip=tunerIP)
            tuner['LineupURL'] = URL_HDHR_LINEUP.format(ip=tunerIP)
            self.tunerDevices.append(tuner)
            logDebug('Devices.addManualTuner:'+xstr(tuner['LocalIP']))

        except Exception as inst:
            logError('Devices.addManualTuner()',inst)
    
###################################################################################################
# Channel collection class definition, that supports both a map and list version of the same data
###################################################################################################
class ChannelCollection:
    def __init__(self,list,map):
        self.list = list
        self.map = map

###################################################################################################
# Channel class definition
###################################################################################################
class Channel:
    def __init__(self,guideNumber,guideName,streamUrl,channelLogo,videoCodec,audioCodec):
        self.number = guideNumber
        self.name = guideName
        self.streamUrl = streamUrl
        self.program = None
        self.logo = channelLogo
        self.videoCodec = videoCodec
        self.audioCodec = audioCodec
        
    def setProgramInfo(self,program):
        self.program = program
    
    def hasProgramInfo(self):
        return (self.program is not None)

###################################################################################################
# Channel class definition
###################################################################################################
class Program:
    def __init__(self,startTime,stopTime,title,date,subTitle,desc,icon,starRating):
        self.startTime = startTime
        self.stopTime = stopTime
        self.title = title
        self.date = date
        self.subTitle = subTitle
        self.desc = desc
        self.icon = icon
        self.starRating = starRating
        self.next = []
    
###################################################################################################
# Favorite class definition
###################################################################################################
class Favorite:
    def __init__(self,index,enable,name,textList,sortBy):
        self.index = index
        self.enable = enable
        self.name = name
        self.tuner = ''
        self.channels = []
        self.totalChannels = 0 
        if textList is not None:
            textListItems = textList.split()
            self.tuner=textListItems[0]
            for item in textListItems:
                try:
                    if isinstance(float(item), float):
                        self.channels.append(item)
                        self.totalChannels = self.totalChannels + 1
                except ValueError:
                    Log.Error("Unable to parse the channel number " + item + " into a number.  Please make sure the list is space separated.")
            if sortBy == 'Channel Number':
                try:
                    self.channels.sort(key=float)
                except Exception as inst:
                    logError('Favorite.channels.sort',inst)

