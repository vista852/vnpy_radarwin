#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time, socket, threading

from vtEngine import MainEngine


def tcplink(sock, addr):
    print 'Accept new connection from %s:%s...' % addr
    sock.send('Welcome!')
    mainEngine = MainEngine()
    mainEngine.ctaEngine.loadSetting()
    while True:
        data = sock.recv(1024)
        time.sleep(1)
        if data == 'exit' or not data:
            break
        #sock.send('Hello, %s!' % data)
        mainEngine.ctaEngine.initStrategy(data)
        mainEngine.ctaEngine.startStrategy(data)
    sock.close()
    print 'Connection from %s:%s closed.' % addr


s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# 监听端口:
s.bind(('172.16.1.128', 9999))
s.listen(5)
print 'Waiting for connection...'

while True:
    # 接受一个新连接:
    sock, addr = s.accept()
    # 创建新线程来处理TCP连接:
    t = threading.Thread(target=tcplink, args=(sock, addr))
    t.start()
