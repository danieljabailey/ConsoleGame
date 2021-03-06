#SpaceHack!  Game server main module
#York Hackspace January 2014
#This runs on a Raspberry Pi

import controls
import mosquitto
import time
import random
import json

sound = True #Swithch this off if you don't have pyGame

def playSound(filename):
    if sound:
        snd = pygame.mixer.Sound("sounds/" + filename)
        snd.play()
        
if sound:
    import pygame
    #Pygame for sounds
    pygame.mixer.quit()
    pygame.mixer.init(48000, -16, 2, 1024) #was 1024
    for fn in controls.soundfiles['continuous']:
        snd = pygame.mixer.Sound("sounds/" + fn)
        snd.play(-1)
    
#MQTT client to allow publishing
client = mosquitto.Mosquitto("PiServer") #ID shown to the broker
server = "127.0.0.1" #Mosquitto MQTT broker running locally


#Game variables
consoles = []
console = {}
currentsetup = {}
currenttimeout = 10.0
lastgenerated = time.time()
numinstructions = 0
gamestate = 'initserver' #initserver, readytostart, waitingforplayers, initgame, setupround, playround, gameover, awardmedals

#Show when we've connected
def on_connect(mosq, obj, rc):
    """Receive MQTT connection notification"""
    if rc == 0:
        print("Connected to MQTT")
    else:
        print("Failed - return code is " + rc)

#MQTT message arrived
def on_message(mosq, obj, msg):
    """Receive and process incoming MQTT published message"""
    nodes = msg.topic.split('/')
    print(msg.topic + " - " + str(msg.payload))
    if nodes[0]=='server':
        if nodes[1]=='register':
            config = json.loads(str(msg.payload))
            consoleip = config['ip']
            console[consoleip] = config
            if not consoleip in consoles:
                consoles.append(consoleip)
            #set console up for game start
            consolesetup = {}
            consolesetup['instructions'] = 'To start new game, all players push and hold button'
            consolesetup['controls'] = {}
            print(config['controls'])
            for control in config['controls']:
                ctrlid = control['id']
                consolesetup['controls'][ctrlid]={}
                if 'gamestart' in control:
                    consolesetup['controls'][ctrlid]['type'] = 'button'
                    consolesetup['controls'][ctrlid]['enabled'] = 1
                    consolesetup['controls'][ctrlid]['name'] = "Push and hold to start"
                else:
                    consolesetup['controls'][ctrlid]['type'] = 'inactive'
                    consolesetup['controls'][ctrlid]['enabled'] = 0
                    consolesetup['controls'][ctrlid]['name'] = ""
                client.subscribe('clients/' + consoleip + '/' + ctrlid + '/value')
            client.publish('clients/' + consoleip + '/configure', json.dumps(consolesetup))
            currentsetup[consoleip] = consolesetup
            global lastgenerated
            global numinstructions
            lastgenerated = time.time()
            numinstructions = 0
    elif nodes[0] == 'clients':
        consoleip = nodes[1]
        ctrlid = nodes[2]
        value = str(msg.payload)
        if currentsetup[consoleip]['controls'][ctrlid]['type'] in ['button', 'toggle', 'selector']:
            value = int(value)
        if nodes[3] == 'value':
            #Check posted value against current targets
            matched = False
            if 'definition' in currentsetup[consoleip]['controls'][ctrlid]:
                currentsetup[consoleip]['controls'][ctrlid]['definition']['value'] = value
            for targetip in consoles:
                consoledef = console[targetip]
                if ('target' in consoledef and consoledef['target']['console'] == consoleip 
                            and consoledef['target']['control'] == ctrlid
                            and str(consoledef['target']['value']) == str(value)):
                    #Match
                    matched = True
                    playSound(random.choice(controls.soundfiles['right']))
                    pickNewTarget(targetip)
            if not matched: #Need to also check if a game round has begun yet
                playSound(random.choice(controls.soundfiles['wrong']))
            
            
#Define a new set of controls for each client for this game round and send it to them as JSON.
def defineControls():
    """Define a new set of controls for each client for this game round and send it to them as JSON."""
    emergency = controls.getEmergency()
    print(emergency)
    for consoleip in consoles:
        print("Defining console " + consoleip)
        consolesetup={}
        consolesetup['instructions']=emergency
        consolesetup['timeout'] = currenttimeout
        consolesetup['controls']={}
        for control in console[consoleip]["controls"]:
            ctrlid = control['id']
            consolesetup['controls'][ctrlid]={}
            consolesetup['controls'][ctrlid]['enabled']=1
            consolesetup['controls'][ctrlid]['name']=controls.getControlName(control['width'], 2, 12)
            ctrldef = random.choice([x for x in control['supported']])
            ctrltype = ctrldef['type']
            if ctrltype in ['words', 'verbs']:
                if ctrldef['fixed']:
                    targetrange = ctrldef['list']
                elif 'safe' in ctrldef and ctrldef['safe']:
                    targetrange=controls.safewords
                elif 'list' in ctrldef:
                    if ctrldef['list']=='allcontrolwords':
                        targetrange=controls.allcontrolwords
                    elif ctrldef['list']=='passwd':
                        targetrange=controls.passwd
                    elif ctrldef['list']=='verbs':
                        targetrange=controls.verbs
                    else:
                        targetrange = controls.allcontrolwords
                elif ctrltype=='verbs':
                    targetrange = controls.verbs
                else:
                    targetrange = controls.allcontrolwords
                #Create a predetermined list?
                if not ctrldef['fixed']:
                    reallyfinished = False
                    while not reallyfinished:
                        wordpool = []
                        finished=False
                        while not finished:
                            newword = random.choice(targetrange)
                            if not newword in wordpool:
                                wordpool.append(newword)
                            if len(wordpool) == ctrldef['quantity']:
                                finished=True
                        if ctrldef['quantity'] != 2 or len(wordpool[0]) + len(wordpool[1]) < 14:
                            reallyfinished = True
                    ctrldef['pool'] = sorted(wordpool)
                else:
                    ctrldef['pool'] = ctrldef['list']
            #Pick a starting value
            if 'assignable' in ctrldef and ctrldef['assignable']:
                if ctrltype in ['words', 'verbs']:
                    ctrldef['value']=random.choice(ctrldef['pool'])
                elif ctrltype == 'selector':
                    ctrldef['value'] = random.choice(range(ctrldef['min'],ctrldef['max']+1))
                elif ctrltype == 'colour':
                    ctrldef['value'] = random.choice(ctrldef['values'])
                elif ctrltype == 'toggle':
                    ctrldef['value'] = random.choice(range(2))
                elif ctrltype == 'button':
                    ctrldef['value'] = 0
                elif ctrltype == 'pin':
                    ctrldef['value'] = ''
            consolesetup['controls'][ctrlid]['type'] = ctrltype
            consolesetup['controls'][ctrlid]['definition']=ctrldef
            print("Control " + ctrlid + " is " + ctrldef['type'] + ": " + consolesetup['controls'][ctrlid]['name'])

        currentsetup[consoleip]=consolesetup
        client.publish('clients/' + consoleip + '/configure', json.dumps(consolesetup))

#Get a choice from a range that isn't the same as the old value
def getChoice(choicerange, oldval):
    """Get a choice from a range that isn't the same as the old value."""
    finished=False
    while not finished:
        retval = random.choice(choicerange)
        if retval != oldval:
            finished=True
    return retval

#Pick a new instruction to display on a given console
def pickNewTarget(consoleip):
    """Pick a new instruction to display on a given console."""
    #pick a random console and random control from that console
    targetconsole = random.choice(consoles)
    targetsetup = currentsetup[targetconsole]
    targetctrlid = random.choice(targetsetup['controls'].keys())
    targetcontrol = targetsetup['controls'][targetctrlid]
    targetname = targetcontrol['name']
    targetdef = targetcontrol['definition']
    targetinstruction = ''
    #pick a new target based on the control type and current value
    ctrltype = targetcontrol['type']
    if 'value' in targetdef:
        curval = targetdef['value']
    else:
        curval=''
    if ctrltype == 'button':
        targetval=1
        targetinstruction = controls.getButtonAction(targetname)
    elif ctrltype == 'toggle':
        if curval == 0:
            targetval=1
        else:
            targetval=0
        targetinstruction = controls.getToggleAction(targetname, targetval)
    elif ctrltype == 'selector':
        targetrange = range(targetdef['min'],targetdef['max']+1)
        targetval = getChoice(targetrange, curval)
        targetinstruction = controls.getSelectorAction(targetname, targetrange, targetval, curval)
    elif ctrltype == 'colour':
        targetrange = targetdef['values']
        targetval = getChoice(targetrange, curval)
        targetinstruction = controls.getColourAction(targetname, targetval)
    elif ctrltype in ['words', 'verbs']:
        targetrange = targetdef['pool']
        targetval=getChoice(targetrange, curval)
        if 'list' in targetdef:
            if targetdef['list']=='passwd':
                targetinstruction = controls.getPasswdAction(targetname, targetval)
            elif targetdef['list']=='verbs' or ctrltype == 'verbs':
                targetinstruction = controls.getVerbListAction(targetname, targetval)
        elif ctrltype == 'verbs':
            targetinstruction = controls.getVerbListAction(targetname, targetval)
        if targetinstruction=='':
            targetinstruction = controls.getWordAction(targetname, targetval)
    elif ctrltype == 'pin':
        finished=False
        while not finished:
            newpin=''
            for i in range(4):
                newpin += str(random.choice(range(10)))
            if newpin != curval:
                finished=True
        targetval=newpin
        targetinstruction = controls.getPinAction(targetname, targetval)
    else:
        print("Unhandled type: " + ctrltype)
    #Now we have targetval and targetinstruction for this consoleip, store and publish it
    console[consoleip]['instructions']=targetinstruction
    console[consoleip]['target']={"console": targetconsole, "control": targetctrlid, "value": targetval, "timestamp": time.time()}
    print("Instruction: " + consoleip + '/' + targetctrlid + ' - ' + str(targetinstruction))
    client.publish('clients/' + consoleip + '/instructions', str(targetinstruction))

def checkTimeouts():
    """Check all targets for expired instructions"""
    for consoleip in consoles:
        consoledef = console[consoleip]
        if 'target' in consoledef and consoledef['target']['timestamp'] + currenttimeout < time.time():
            #Expired instruction
            playSound(random.choice(controls.soundfiles['wrong']))
            pickNewTarget(consoleip)

    
#Main loop

#Connect to MQTT (final code should make this a retry loop)
client.on_connect = on_connect
client.on_message = on_message
client.connect(server)

#Main topic subscription point for clients to register their configurations to
client.subscribe('server/register')

client.publish('server/ready', 'started')

while(client.loop() == 0): 
    #Every five seconds...
    if time.time()-lastgenerated > currenttimeout: 
        client.publish('server/ready', 'ready')
        if len(consoles) > 0:
            if numinstructions == 0:
                #temp
                playSound(random.choice(controls.soundfiles['atmosphere']))
                #Dump another batch of random control names and action
                defineControls()
                numinstructions = 5
            else:
                #temp
                playSound(random.choice(controls.soundfiles['right']))
                for consoleip in consoles:
                    pickNewTarget(consoleip)
                numinstructions -= 1
        lastgenerated = time.time()

#If client.loop() returns non-zero, loop drops out to here.
#Final code should try to reconnect to MQTT and/or networking if so.
