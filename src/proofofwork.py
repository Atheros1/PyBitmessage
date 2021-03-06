#import shared
#import time
#from multiprocessing import Pool, cpu_count
import hashlib
from struct import unpack, pack
import sys
from shared import config, frozen, codePath
import shared
import openclpow
import os
import ctypes

bitmsglib = 'bitmsghash.so'
if "win32" == sys.platform:
    if ctypes.sizeof(ctypes.c_voidp) == 4:
        bitmsglib = 'bitmsghash32.dll'
    else:
        bitmsglib = 'bitmsghash64.dll'
    try:
        bso = ctypes.WinDLL(os.path.join(codePath(), "bitmsghash", bitmsglib))
    except:
        bso = None
else:
    try:
        bso = ctypes.CDLL(os.path.join(codePath(), "bitmsghash", bitmsglib))
    except:
        bso = None
if bso:
    try:
        bmpow = bso.BitmessagePOW
        bmpow.restype = ctypes.c_ulonglong
    except:
        bmpow = None
else:
    bmpow = None

def _set_idle():
    if 'linux' in sys.platform:
        import os
        os.nice(20)  # @UndefinedVariable
    else:
        try:
            sys.getwindowsversion()
            import win32api,win32process,win32con  # @UnresolvedImport
            pid = win32api.GetCurrentProcessId()
            handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
            win32process.SetPriorityClass(handle, win32process.IDLE_PRIORITY_CLASS)
        except:
            #Windows 64-bit
            pass

def _pool_worker(nonce, initialHash, target, pool_size):
    _set_idle()
    trialValue = float('inf')
    while trialValue > target:
        nonce += pool_size
        trialValue, = unpack('>Q',hashlib.sha512(hashlib.sha512(pack('>Q',nonce) + initialHash).digest()).digest()[0:8])
    return [trialValue, nonce]

def _doSafePoW(target, initialHash):
    print "Safe POW\n"
    nonce = 0
    trialValue = float('inf')
    while trialValue > target:
        nonce += 1
        trialValue, = unpack('>Q',hashlib.sha512(hashlib.sha512(pack('>Q',nonce) + initialHash).digest()).digest()[0:8])
    return [trialValue, nonce]

def _doFastPoW(target, initialHash):
    print "Fast POW\n"
    import time
    from multiprocessing import Pool, cpu_count
    try:
        pool_size = cpu_count()
    except:
        pool_size = 4
    try:
        maxCores = config.getint('bitmessagesettings', 'maxcores')
    except:
        maxCores = 99999
    if pool_size > maxCores:
        pool_size = maxCores
    pool = Pool(processes=pool_size)
    result = []
    for i in range(pool_size):
        result.append(pool.apply_async(_pool_worker, args = (i, initialHash, target, pool_size)))
    while True:
        if shared.shutdown >= 1:
            pool.terminate()
            while True:
                time.sleep(10) # Don't let this thread return here; it will return nothing and cause an exception in bitmessagemain.py
            return
        for i in range(pool_size):
            if result[i].ready():
                result = result[i].get()
                pool.terminate()
                pool.join() #Wait for the workers to exit...
                return result[0], result[1]
        time.sleep(0.2)
def _doCPoW(target, initialHash):
    h = initialHash
    m = target
    out_h = ctypes.pointer(ctypes.create_string_buffer(h, 64))
    out_m = ctypes.c_ulonglong(m)
    print "C PoW start"
    nonce = bmpow(out_h, out_m)
    trialValue, = unpack('>Q',hashlib.sha512(hashlib.sha512(pack('>Q',nonce) + initialHash).digest()).digest()[0:8])
    print "C PoW done"
    return [trialValue, nonce]

def _doGPUPoW(target, initialHash):
    print "GPU PoW start"
    nonce = openclpow.do_opencl_pow(initialHash.encode("hex"), target)
    trialValue, = unpack('>Q',hashlib.sha512(hashlib.sha512(pack('>Q',nonce) + initialHash).digest()).digest()[0:8])
    #print "{} - value {} < {}".format(nonce, trialValue, target)
    print "GPU PoW done"
    return [trialValue, nonce]

def run(target, initialHash):
    target = int(target)
    if shared.safeConfigGetBoolean('bitmessagesettings', 'opencl') and openclpow.has_opencl():
#        trialvalue1, nonce1 = _doGPUPoW(target, initialHash)
#        trialvalue, nonce = _doFastPoW(target, initialHash)
#        print "GPU: %s, %s" % (trialvalue1, nonce1)
#        print "Fast: %s, %s" % (trialvalue, nonce)
#        return [trialvalue, nonce]
        try:
            return _doGPUPoW(target, initialHash)
        except:
            pass # fallback
    if bmpow:
        try:
            return _doCPoW(target, initialHash)
        except:
            pass # fallback
    if frozen == "macosx_app" or not frozen:
        # on my (Peter Surda) Windows 10, Windows Defender
        # does not like this and fights with PyBitmessage
        # over CPU, resulting in very slow PoW
        try:
            return _doFastPoW(target, initialHash)
        except:
            pass #fallback
    return _doSafePoW(target, initialHash)
