"""Independent Python/OpenSSL test peer for actual JVM production bridge socket.
Synthetic keys/identity only. No frames or payload-derived exceptions are printed.
The same phone/control driver is required against actual Native in Simulator.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile

def load(name, filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

if __name__ == '__main__':
    cid=load('live_cid','test-fe36-cid-simulator.py')
    wire=load('live_wire','test-fe35-cli-inbound-simulator.py')
    if not shutil.which('openssl'):
        existing=Path('C:/Program Files/Git/usr/bin/openssl.exe')
        if existing.is_file():os.environ['PATH']=str(existing.parent)+os.pathsep+os.environ['PATH']
    try:
        with tempfile.TemporaryDirectory(prefix='nearby-test-phone-') as folder:
            with socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=4) as tcp:
                cid.live_control(tcp,None,wire,Path(folder),'wifi_live_disconnect',0,lambda _:None)
        print('NEARBY_PYTHON_OPENSSL_JVM_SOCKET_OK;SYNTHETIC_PHONE_NOT_DEVICE')
    except Exception as error:
        print('NEARBY_PYTHON_PHONE_FAIL='+cid.safe_exception_name(error)+':'+cid.safe_label(str(error)))
        sys.exit(1)
