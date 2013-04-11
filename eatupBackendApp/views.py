import os, re, time, datetime, urllib, math, requests
from django.conf import settings
from django.http import (HttpResponse, HttpResponseBadRequest, 
                         HttpResponseServerError, HttpResponseForbidden, 
                         HttpResponseRedirect, HttpResponseNotFound)
from eatupBackendApp.models import Event, AppUser, Location
from eatupBackendApp.json_response import json_response
import eatupBackendApp.imageUtil as imageUtil
from annoying.functions import get_object_or_None 
from django.shortcuts import render
from django.utils.timezone import utc
from django.views.decorators.csrf import csrf_exempt

try:
    import json
except ImportError:
    import simplejson as json

### helper functions ###
  
def parseIntOrNone(intStr):
    '''(string): integer or None

    attempts to parse the input into an integer, returns None if it fails
    '''  
    try:
        output = int(intStr)
    except:
        output = None
    return output  

def parseLongOrNone(longStr):
    try:
        output = long(longStr)
    except:
        output = None
    return output     
    
def parseFloatOrNone(floatStr):
    '''(string): float or None

    attempts to parse the input into a non-NaN float, returns None if it fails
    '''  
    try:
        output = float(floatStr)
        assert not math.isnan(output)
    except:
        output = None
    return output
    
def createErrorDict(errorMsg="an error occurred"):
    '''(string): dict

    returns a simple dictionary with an "error" entry
    '''  
    return {'error': errorMsg}
    
def jsonDictOfSpecificObj(modelClass, pk, errorMsg="invalid"):
    '''(models.Model subclass, <primary key type>, string): dict
    
    finds the model object with the specific given primary key and returns its
    JSON-friendly dictionary representation
    returns an error dictionary if no such object exists
    '''
    foundObj = get_object_or_None(modelClass, pk=pk)
    if foundObj is None:
        return createErrorDict(errorMsg)
    else:
        return foundObj.getDictForJson()
    
def getDictArray(reqDict, name):
    '''(request dictionary, string): dictionary list, bool
    
    modified from http://stackoverflow.com/a/5498916
    takes the weirdly-parsed request.REQUEST dict from some django request that
    was passed a list of json objects
    and parses it into a list of Python dictionaries
    
    name is the name of the json property whose value was a list of objects
    
    NOTE: only works for arrays of one-level objects
    
    always returns an array (returns an empty list if given invalid name)
    
    also returns whether or not it was able to find the name or not
    '''
    exists = False
    dic = {}
    for k in reqDict.keys():
        if k.startswith(name):
            exists = True
            rest = k[len(name):]
            if len(rest) == 0:
                continue

            # split the string into different components
            parts = [p[:-1] for p in rest.split('[')][1:]
            id = int(parts[0].replace("\"", ""))

            # add a new dictionary if it doesn't exist yet
            if id not in dic:
                dic[id] = {}

            # add the information to the dictionary
            dic[id][parts[1]] = reqDict.get(k)
            
    
    # because dic is a dictionary of listindeces mapped to the actual 
    # sub-dictionary at that index, return the list of sub-dictionaries instead
    keyVals = sorted(dic.items())
    return map(lambda (i, subDict): subDict, keyVals), exists
   

def locationDictToObject(locDict, allowCreation=True, allowEditing=False, 
                         parentEvent=None):
    ''' (dict, bool, bool): Location, string

    validates and turns a dictionary of some location's attributes into its
    respective Location object
    
    if allowCreation is True and no preexisting id is given, 
    creates a new Location and returns it (up to caller to save to the database)
     - this will require data for all required fields
     
    if allowCreation is False and no preexisting id is given, returns an error
    
    if a preexisting id is given and allowEditing is True, 
    edits the Location to match the given attributes
    
    if a preexisting id is given and allowEditing is False, returns an error
    
    returns errors if validation fails at any point 
    (up to caller to save changes)
    
    return two values:
      - a Location object, if validation passes, None otherwise
      - None if validation passes, an error message otherwise
      
    NOTE: does not handle saving the eventHere relationship, this is left to 
    the caller
    '''
    # first, parse out the location's attributes
    latitude = locDict.get('lat')
    longitude = locDict.get('lng')
    friendlyName = locDict.get("friendly_name")
    link = locDict.get("link")
    numVotes = locDict.get("num_votes", 0)
    # ensure that the number of votes is a nonnegative int
    if type(numVotes) != int:
        numVotes = parseIntOrNone(numVotes)
        if numVotes is None or numVotes < 0:
            return (None, "invalid number of votes given")
            
    # search for ID of preexisting location object        
    id = parseIntOrNone(locDict.get('id', ""))
    existingLoc = get_object_or_None(Location, id=id)
    outputLoc = None
    # if preexisting object, edit its attributes
    if existingLoc is not None:
        if allowEditing:
            if parentEvent is None or existingLoc.eventHere == parentEvent:
                existingLoc.lat = latitude
                existingLoc.lng = longitude
                existingLoc.friendly_name = friendlyName
                existingLoc.link = link
                existingLoc.num_votes = numVotes
                outputLoc = existingLoc
            else:
                return (None, 'not allowed to modify location ID %d' % id)
        else:
            return (None, "location ID %d already exists" % id)
    # if no preexisting object and creation is allowed, create new Location
    elif allowCreation:
        outputLoc = Location(lat=latitude, lng=longitude, 
                             friendly_name=friendlyName,
                             link=link, num_votes=numVotes)
    # otherwise, return error
    else:
        return (None, ("location id not given, "
                       "new location creation not allowed"))
                       
    # validate model before returning it                       
    try:
        outputLoc.full_clean()
    except Exception as e:
        return (None, str(e))
    return (outputLoc, None)
        
def parseElems(unparsedElems, parseFn, elemName="element"):
    ''' ('a list, 'a -> 'b, string): ('b list or None, string or None)
    
    applies the given parsing function to every element in the given list
    
    returns two values:
      - the list of parsed elements if no error occurs, None otherwise
      - None if no error occurs, an error message otherwise
    '''
    parsedElems = []
    for elem in unparsedElems:
        try: 
            parsedElem = parseFn(elem)
        except:
            return (None, "unable to parse %s %s" % (elemName, elem))
        parsedElems.append(parsedElem)
    return (parsedElems, None)

def idToObject(parsedId, objType, objName="object"):
    ''' (<id type>, models.Model subclass, string): model instance
    
    takes an already-parsed id (ie: already converted from string)
    and creates a list of model objects with those ids
    returns two values as a tuple: 
    - the objects, if it is found (None otherwise)
    - None if no error occurs, otherwise an error message
    '''
    foundObj = get_object_or_None(objType, pk=parsedId)
    if foundObj is None:
        return (None, 'invalid %s ID %r' % (objName, parsedId))
    else:
        return foundObj, None
    
def idsToObjects(parsedIdList, objType, objName="object"):
    ''' (<id type> list, models.Model subclass, string): model instance list
    
    takes a list of already-parsed ids (ie: already converted from strings)
    and creates a list of model objects with those ids
    returns two values as a tuple: 
    - the list of objects, if they are all found (None otherwise)
    - None if no error occurs, otherwise an error message
    '''
    objects = []
    for parsedId in parsedIdList:
        foundObj, error = idToObject(parsedId, objType, objName)
        if (error): 
            return None, error
        objects.append(foundObj)
    return (objects, None)       
    
    
def parseIdsToObjects(unparsedIds, objType, parseFn, objName="object"):
    ''' ('a list, models.Model subclass, 'a -> id type, string):
        model instance list
    
    takes a list of unparsed ids, parses it into a list of ids, then
    creates a list of model objects with those ids
    
    returns two values as a tuple: 
    - the list of objects if no parsing or locating error occurs, None otherwise
    - None if no error occurs, otherwise an error message
    '''
    parsedIds, error = parseElems(unparsedIds, parseFn, 
                                  elemName=("%s ID" % objName))
    if error:
        return (None, error)
        
    objects, error = idsToObjects(parsedIds, objType, objName=objName)
    if error:
        return (None, error)
        
    return (objects, None)
        
def parseTimestamp(timestampStr):    
    timestampVal = parseIntOrNone(timestampStr)
    
    if timestampVal == None:
        return None, "invalid timestamp"
        
    # account for fact that javascript timestamps are in milliseconds while
    # python's are in seconds
    timestampVal /= 1000
    
    # turn timestamp into an actual datetime object
    try:
        newDateTime = datetime.datetime.fromtimestamp(timestampVal, utc)
    except ValueError:
        return None, 'invalid timestamp'
        
    return newDateTime, None
    
def getUpdatedLocations(newLocationsData, allowCreation=False, 
                        allowEditing=True, parentEvent=None):   
    # for every location data, update locations as needed and storedthe 
    # new object, but don't save to the database
    # during the initial runthrough. Does not save the updated location objects,
    # up to caller to called location.save() to update the database
    eventLocations = []
    for i in xrange(len(newLocationsData)):
        locationData = newLocationsData[i]
        newLocation, error = locationDictToObject(locationData, 
                                                  allowCreation=allowCreation,
                                                  allowEditing=allowEditing,
                                                  parentEvent=parentEvent)
        if error:
            return None, "invalid location data at index %d: %s" % (i, error)
        eventLocations.append(newLocation)
    
    return eventLocations, None        
    
def isListInRequestDict(dataDict, listName):
    if listName.endswith("[]"):
        return listName in dataDict or listName[:-2] in dataDict
    else:
        return listName in dataDict or ("%s[]" % listName) in dataDict
    
### url-view functions ###    

def showIndex(request):
    return render(request, 'index.html', {})    
    
@json_response()    
def getUser(request):
    if 'uid' not in request.REQUEST:
        return createErrorDict('missing id argument')
    
    uid = parseLongOrNone(request.REQUEST['uid'])
    if uid is None:
        return createErrorDict('invalid user')
        
    return jsonDictOfSpecificObj(AppUser, uid, errorMsg="invalid user")
    
@json_response()    
def getEvent(request):
    if 'eid' not in request.REQUEST:
        return createErrorDict('missing id argument')
    
    eid = parseIntOrNone(request.REQUEST['eid'])
    if eid is None:
        return createErrorDict('invalid event')
    
    return jsonDictOfSpecificObj(Event, eid, errorMsg="invalid event")       

@json_response()    
def getUserEvents(request):
    if 'uid' not in request.REQUEST:
        return createErrorDict('missing id argument')
    
    uid = parseLongOrNone(request.REQUEST['uid'])
    if uid is None:
        return createErrorDict('invalid user')
        
    requestedUser = get_object_or_None(AppUser, uid=uid)
    if requestedUser is None:
        return createErrorDict('user does not exist')
    
    outputJsonDicts = []
    for participatingEvent in requestedUser.participating.all():
        outputJsonDicts.append(participatingEvent.getDictForJson())
        
    return {
        "uid": uid,
        "events": outputJsonDicts
    }    
    
    
def updateAndSaveEvent(dataDict, creationMode=False):
    parsedEventId = parseIntOrNone(dataDict.get('eid'))
    if creationMode == False:
        if parsedEventId is None:
            return createErrorDict("missing event ID")
        newEvent = get_object_or_None(Event, eid=parsedEventId)
        if newEvent is None:
            return createErrorDict("invalid event ID %s" % parsedEventId)
    else:
        # don't initialize any attributes yet, wait until
        # parsing rest of attributes before setting attributes
        newEvent = Event()
    
    rawHostId = dataDict.get("host")
    rawTitle = dataDict.get("title")
    rawDesc = dataDict.get("description")
    rawTimestamp = dataDict.get("date_time_raw")
    
    # check for 'participants' to also check for case where we are trying to 
    # clear the list of participants
    participantsGiven = isListInRequestDict(dataDict, "participants[]")
    rawParticipantIds = dataDict.getlist("participants[]")
    rawLocationsData, locationsGiven = getDictArray(dataDict, "locations")
    
    changeDict = {
        'title': None,
        'date_time': None,
        'description': None,
        'host': None
    }
    newParticipants = None
    newLocations = None
    
    # load simple attribute dictionary
    if rawTitle is None:
        if creationMode:
            changeDict['title'] = ''
    else:
        changeDict['title'] = rawTitle
        
    if rawDesc is None:
        if creationMode:
            changeDict['description'] = ''
    else:
        changeDict['description'] = rawDesc
        
    if rawTimestamp is None:
        if creationMode:
            return createErrorDict('timestamp is required')
    else:
        newDateTime, error = parseTimestamp(rawTimestamp)
        if error: return createErrorDict(error)
        changeDict['date_time'] = newDateTime
    
    if rawHostId is None:
        if creationMode:
            return createErrorDict("host user's ID is required")
    else:
        parsedHostId = parseLongOrNone(rawHostId)
        if parsedHostId is None:
            return createErrorDict("invalid format for host user ID given")
        newHost = get_object_or_None(AppUser, uid=parsedHostId)
        if newHost is None:
            return createErrorDict("invalid host user ID given")
        changeDict['host'] = newHost
        # add to participants list if not already there
        if rawHostId not in rawParticipantIds:
            rawParticipantIds.append(rawHostId)
            participantsGiven = True
    
    # retrieve values for to-many fields
    if participantsGiven:
        newParticipants, error = parseIdsToObjects(rawParticipantIds, AppUser,
                                                   lambda s: int(s), 
                                                   objName="participant")
        if error: return createErrorDict(error)
        
    if locationsGiven:
        newLocations, error = getUpdatedLocations(rawLocationsData, 
                                                  allowCreation=True,
                                                  allowEditing=True,
                                                  parentEvent=newEvent)
        if error: return createErrorDict(error)
        
    # finally, update the events' simple attributes
    for key in changeDict.keys():
        if changeDict[key] is None:
            continue
        setattr(newEvent, key, changeDict[key])
    
    # check for validity before committing to any changes
    try:
        newEvent.full_clean()
    except Exception as e:
        return createErrorDict(str(e))    
    
    # finally, save locations and events
    newEvent.save()
    
    if newLocations is not None:
        for loc in newLocations:
            loc.save()
        newEvent.locations.clear()
        newEvent.locations.add(*newLocations)
        
        # clean up newly orphaned locations
        Location.objects.filter(eventHere=None).delete()
        
    if newParticipants is not None:
        if newEvent.host not in newParticipants:
            newParticipants.append(newEvent.host)
        newEvent.participants.clear()
        newEvent.participants.add(*newParticipants)
    
    return {'status':'ok',
            'eid': newEvent.pk}
    
@json_response() 
@csrf_exempt
def createEvent(request):
    # change this to POST if it turns out ios apps don't have to worry about
    # cross domain policy
    dataDict = request.REQUEST
    print dataDict
    
    return updateAndSaveEvent(dataDict, creationMode=True)
    
@json_response()
def editEvent(request):
    dataDict = request.REQUEST
    return updateAndSaveEvent(dataDict, creationMode=False)
    
def updateAndSaveUser(dataDict, creationMode=False):
    if 'uid' not in dataDict:
        return createErrorDict("facebook uid is required")
    uid = parseLongOrNone(dataDict['uid'])
    
    existingUser = get_object_or_None(AppUser, uid=uid)
    if uid is None or uid < 0:
        return createErrorDict("invalid uid given; incorrect format")
    elif creationMode and existingUser is not None:
        return createErrorDict("cannot create user %d, already exists" %uid)
    elif not creationMode and existingUser is None:
        return createErrorDict("cannot edit user %d, does not exist" % uid)
    
    # either set as existing user or create a new one
    currUser = existingUser if existingUser is not None else AppUser(uid=uid)
    
    rawFirstName = dataDict.get("first_name")
    rawLastName = dataDict.get("last_name")
    
    # parse participating IDs and friend IDs into lists of Events and AppUsers,
    # respectively
    participatingGiven = isListInRequestDict(dataDict, "participating[]")
    rawParticipatingIds = dataDict.getlist('participating[]')
    newParticipating = []
    friendsGiven = isListInRequestDict(dataDict, "friends[]")
    rawFriendIds = dataDict.getlist('friends[]')
    newFriends = []
    
    if rawFirstName is not None:
        currUser.first_name = rawFirstName
        
    if rawLastName is not None:
        currUser.last_name = rawLastName
        
    if participatingGiven:
        newParticipating, error = parseIdsToObjects(rawParticipatingIds, Event,
                                                    lambda s: int(s), 
                                                    objName="participating")
        if error: return createErrorDict(error)
        
    if friendsGiven:
        newFriends, error = parseIdsToObjects(rawFriendIds, AppUser, 
                                              lambda s: int(s),
                                              objName="friend")
        if error: return createErrorDict(error)   
    
    # check for valid profile picture url, if given    
    profPicUrl = dataDict.get("prof_pic")
    profPicContent = None
    profPicFiletype = None
    if profPicUrl is not None:
        if profPicUrl != "":
            try:
                profPicContent, profPicFiletype = \
                    imageUtil.getImageUrlContentAndType(profPicUrl)
            except ValueError as e:
                return createErrorDict(str(e))
        # delete profile picture if prompted to        
        else:
            currUser.prof_pic = None
    
    # validate the new AppUser object                     
    try:
        currUser.full_clean()
    except Exception as e:
        return createErrorDict(str(e))    
    
    # save the user
    currUser.save()
         
    if participatingGiven:
        currUser.participating.clear()
        currUser.participating.add(*newParticipating)
    
    if friendsGiven:
        currUser.friends.clear()
        currUser.friends.add(*newFriends)
        
    # save profile picture
    if profPicContent and profPicFiletype:
        filename = "profpic_%d.%s" % (currUser.uid, profPicFiletype)
        try:
            imageUtil.saveImageFieldContents(currUser, 'prof_pic', 
                                             profPicContent, filename)
        except Exception as e:
            errorDict = createErrorDict(str(e))
            errorDict['uid'] = currUser.pk
            return errorDict
    
    return {'status': 'ok',
            'uid': currUser.pk}
    
@json_response()   
def createUser(request):
    dataDict = request.REQUEST
    
    output = updateAndSaveUser(dataDict, creationMode=True)
    # remove erroneously created users
    if "error" in output and "uid" in output:
        AppUser.objects.filter(uid=output['uid']).delete()
        del(output['uid'])
        
    return output
    
@json_response()   
def editUser(request):
    dataDict = request.REQUEST
    return updateAndSaveUser(dataDict, creationMode=False)    