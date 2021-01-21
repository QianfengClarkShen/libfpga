import io
import os
import sys
import mmap
import time
import math

def getbit(value,position):
    return (value >> position)&1

def setbit(value,position,bitvaule):
    if bitvaule == 0:
        mask = 0xFFFFFFFF ^ (1 << position)
        return value & mask
    else:
        mask = 1 << position
        return value | mask

def addr_cal(addr,length):
    mem_span = 2**math.ceil(math.log(length,2))
    mem_start = addr-(addr%mem_span)
    if addr%mem_span == 0:
        mem_end = mem_start+mem_span
    else:
        mem_end = mem_start+2*mem_span
    page_start = math.floor(addr/mmap.PAGESIZE)*mmap.PAGESIZE
    page_end = math.ceil((addr+length)/mmap.PAGESIZE)*mmap.PAGESIZE
    mem_start = max(mem_start,page_start)
    mem_end = min(mem_end,page_end)
    mem_span = mem_end-mem_start
    trans_start = addr-mem_start
    return [mem_start, mem_span, trans_start]

class axilite:
    size = -1
    mem = None
    fd = -1
    def __init__(self,addr=0,size=0x1000,xdma_channel=0):
        dev_fpath = '/dev/xdma%d_user' % xdma_channel
        if addr%mmap.PAGESIZE != 0:
            raise Exception('The address you want to map is not page aligned, exiting!')
        if size%mmap.PAGESIZE != 0:
            raise Exception('Minimal allocating unit is one PAGE, exiting!')
        try:
            self.fd=os.open(dev_fpath,os.O_RDWR | os.O_SYNC)
        except IOError:
            raise Exception('Unable to open %s, maybe try with sudo?' % dev_fpath)
        self.size = size
        self.mem = mmap.mmap(self.fd,size,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=addr)
    def __read(self, length, offset):
        real_length = length
        if real_length < 4:
            real_length = 4
        if offset+real_length > self.size:
            print('Trying to read beyond the buffer edge')
            return 1
        mem_start, mem_span, trans_start = addr_cal(offset, real_length)
        self.mem.seek(mem_start)
        raw_bytes=self.mem[mem_start:mem_start+mem_span]
        return raw_bytes[trans_start:trans_start+length]
    def __write(self, raw_bytes, offset):
        length=len(raw_bytes)
        if length < 4:
            length = 4
        if offset+length > self.size:
            print('Trying to write beyond the buffer edge')
            return 1
        mem_start, mem_span, trans_start = addr_cal(offset, length)
        if mem_span > mmap.PAGESIZE:
            tmp_buf = bytearray(mem_span)
            tmp_buf[0:mmap.PAGESIZE] = self.__read(mmap.PAGESIZE,mem_start)
            tmp_buf[mem_span-mmap.PAGESIZE:mem_span] = self.__read(mmap.PAGESIZE,mem_start+mem_span-mmap.PAGESIZE)
        else:
            tmp_buf = bytearray(self.__read(mem_span,mem_start))
        tmp_buf[trans_start:trans_start+len(raw_bytes)] = raw_bytes
        self.mem[mem_start:mem_start+mem_span]=tmp_buf
    def read32(self, offset=0):
        return int.from_bytes(self.__read(4,offset),sys.byteorder)
    def read64(self, offset=0):
        return int.from_bytes(self.__read(8,offset),sys.byteorder)
    def read(self, length, offset=0):
        return self.__read(length,offset)
    def write32(self, value, offset=0):
        raw_bytes = value.to_bytes(4,sys.byteorder)
        return self.__write(raw_bytes,offset)
    def write64(self, value, offset=0):
        raw_bytes = value.to_bytes(8,sys.byteorder)
        return self.__write(raw_bytes,offset)
    def write(self, raw_bytes, offset=0):
        return self.__write(raw_bytes, offset)
    def clean(self):
        if self.mem is not None:
            self.mem.close()
            self.mem = None
        if self.fd > 0:
            os.close(self.fd)
            self.fd = -1

class xdma_h2c:
    fd = None
    def __init__(self,dev_fpath='/dev/xdma0_h2c_0'):
        try:
            self.fd = os.open(dev_fpath,os.O_RDWR)
        except IOError:
            raise Exception('Unable to open %s, maybe try with sudo?' % dev_fpath)
    def transfer(self,raw_bytes,addr=0):
        if addr%mmap.PAGESIZE != 0:
            raise Exception('The address you want to map is not page aligned, exiting!')
        if addr != 0:
            os.lseek(self.fd,addr,0)
        os.write(self.fd,raw_bytes)
    def clean(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

class xdma_c2h:
    fd = None
    def __init__(self,dev_fpath='/dev/xdma0_c2h_0'):
        try:
            self.fd = os.open(dev_fpath,os.O_RDWR)
        except IOError:
            raise Exception('Unable to open %s, maybe try with sudo?' % dev_fpath)
    def transfer(self,size,addr=0):
        if addr%mmap.PAGESIZE != 0:
            raise Exception('The address you want to map is not page aligned, exiting!')
        if addr != 0:
            os.lseek(self.fd,addr,0)
        return os.read(self.fd,size)
    def clean(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

class fpgamem:
    h2c = None
    c2h = None
    fpgabase_addr = 0
    def __init__(self,h2c_fpath='/dev/xdma0_h2c_0',c2h_fpath='/dev/xdma0_c2h_0',fpgamem_mapbase=0):
        self.h2c = xdma_h2c(h2c_fpath)
        self.c2h = xdma_c2h(c2h_fpath)
        self.fpgabase_addr = fpgamem_mapbase
    def get(self,fpgaoffset=0,size=4096):
        return self.c2h.transfer(size,fpgaoffset)
    def put(self,raw_bytes,fpgaoffset=0):
        self.h2c.transfer(raw_bytes,fpgaoffset)
    def file2mem(self,f,fpgaoffset=0,size=-1):
        if isinstance(f,io.BufferedIOBase):
            fd=f
        elif isinstance(f,str):
            fd=open(f,'rb')
        else:
            print('ERROR: input file should be in binary format')
            return 1
        size_to_read = 0x7ffff000 #size limit
        fpgaaddr=self.fpgabase_addr+fpgaoffset
        while True:
            raw_bytes = fd.read(size_to_read)
            if len(raw_bytes) == 0:
                break
            self.put(raw_bytes,fpgaaddr)
            fpgaaddr+=size_to_read
        if isinstance(f,str):
            fd.close()
    def mem2file(self,f,fpgaoffset=0,size=4096):
        if isinstance(f,io.BufferedIOBase):
            fd=f
        elif isinstance(f,str):
            fd=open(f,'wb')
        else:
            print('ERROR: output file should be in binary format')
            return 1
        remain_size = size
        fpgaaddr=self.fpgabase_addr+fpgaoffset
        while remain_size > 0:
            bytes_to_read = min(remain_size,0x7ffff000)
            remain_size -= bytes_to_read
            raw_bytes = self.get(fpgaaddr,bytes_to_read)
            fd.write(raw_bytes)
            fpgaaddr+=bytes_to_read
            if len(raw_bytes) != bytes_to_read:
                break
        if isinstance(f,str):
            fd.close()
    def clean(self):
        if self.h2c is not None:
            self.h2c.clean()
            self.h2c = None
        if self.c2h is not None:
            self.c2h.clean()
            self.c2h = None
