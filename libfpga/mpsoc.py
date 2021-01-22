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

def __get_phy_buf_addr():
    fd = open('/sys/class/u-dma-buf/phy_buf/phys_addr','r')
    phy_addr = int(fd.read().rstrip(),16)
    fd.close()
    return phy_addr

def __get_phy_buf_size():
    fd = open('/sys/class/u-dma-buf/phy_buf/size','r')
    size = int(fd.read().rstrip())
    fd.close()
    return size

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
    trans_end = trans_start + length
    return [mem_start, mem_span, trans_start, trans_end]

system_buf_addr=__get_phy_buf_addr()
system_buf_size=__get_phy_buf_size()

class axilite:
    size = -1
    mem = None
    fd = -1
    def __init__(self,addr=0,size=0x1000):
        if addr%mmap.PAGESIZE != 0:
            raise Exception('The address you want to map is not page aligned, exiting!')
        if size%mmap.PAGESIZE != 0:
            raise Exception('Minimal allocating unit is one PAGE, exiting!')
        try:
            self.fd=os.open('/dev/mem',os.O_RDWR | os.O_SYNC)
        except IOError:
            raise Exception('Unable to open /dev/mem, maybe try with sudo?')    
        self.size = size
        self.mem = mmap.mmap(self.fd,size,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=addr)
    def __read(self, length, offset):
        if offset+length > self.size:
            print('Trying to read beyond the buffer edge')
            return 1
        mem_start, mem_span, trans_start, trans_end = addr_cal(offset, length)
        self.mem.seek(mem_start)
        raw_bytes=self.mem.read(mem_span)
        return raw_bytes[trans_start:trans_end]
    def __write(self, raw_bytes, offset):
        length=len(raw_bytes)
        if offset+length > self.size:
            print('Trying to write beyond the buffer edge')
            return 1            
        mem_start, mem_span, trans_start, trans_end = addr_cal(offset, length)
        if mem_span > mmap.PAGESIZE:
            tmp_buf = bytearray(mem_span)
            tmp_buf[0:mmap.PAGESIZE] = self.__read(mmap.PAGESIZE,mem_start)
            tmp_buf[mem_span-mmap.PAGESIZE:mem_span] = self.__read(mmap.PAGESIZE,mem_start+mem_span-mmap.PAGESIZE)
        else:
            tmp_buf = bytearray(self.__read(mem_span,mem_start))
        tmp_buf[trans_start:trans_end] = raw_bytes
        self.mem.seek(mem_start)
        self.mem.write(tmp_buf)
        return 0
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

class phy_buf:
    size = system_buf_size
    mem = None
    mem_fd = -1
    phy_addr = system_buf_addr
    offset = 0
    def __init__(self,offset=0,size=system_buf_size):
        if size+offset > system_buf_size:
            raise Exception('System has in total '+ str(system_buf_size) +' bytes reserve memory, requsting buffer is beyond that edge, exiting!')
        if offset%mmap.PAGESIZE != 0:
            raise Exception('The address you want to allocate is not page aligned, exiting!')
        if size%mmap.PAGESIZE != 0:
            raise Exception('Minimal allocating unit is one PAGE, exiting!')
        if not os.path.exists('/dev/phy_buf'):
            raise Exception('Physical buffer not exist, exiting!')
        try:
            self.mem_fd = os.open('/dev/phy_buf', os.O_RDWR | os.O_SYNC)
        except IOError:
            raise Exception('Unable to open /dev/phy_buf!')
        self.phy_addr = system_buf_addr+offset
        self.size = size
        self.mem = mmap.mmap(self.mem_fd,size,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=offset)
    def read(self, length, offset=0):
        if offset+length > self.size:
            print('Trying to read beyond the buffer edge')
            return 1
        mem_start, mem_span, trans_start, trans_end = addr_cal(offset, length)
        self.mem.seek(mem_start)
        raw_bytes=self.mem.read(mem_span)
        return raw_bytes[trans_start:trans_end]
    def write(self, raw_bytes, offset=0):
        length=len(raw_bytes)
        if offset+length > self.size:
            print('Trying to write beyond the buffer edge')
            return 1
        mem_start, mem_span, trans_start, trans_end = addr_cal(offset, length)
        if mem_span > mmap.PAGESIZE:
            tmp_buf = bytearray(mem_span)
            tmp_buf[0:mmap.PAGESIZE] = self.read(mmap.PAGESIZE,mem_start)
            tmp_buf[mem_span-mmap.PAGESIZE:mem_span] = self.read(mmap.PAGESIZE,mem_start+mem_span-mmap.PAGESIZE)
        else:
            tmp_buf = bytearray(self.read(mem_span,mem_start))
        tmp_buf[trans_start:trans_end] = raw_bytes    
        self.mem.seek(mem_start)
        self.mem.write(tmp_buf)
        return 0
    def clean(self):
        if self.mem is not None:
            self.mem.close()
            self.mem = None
        if self.mem_fd > 0:
            os.close(self.mem_fd)
            self.mem_fd = -1

class axidma:
    axil = None
    phy_buf = None
    bufsize = system_buf_size
    dma_bufsize = 2**26
    ps_phy_addr = system_buf_addr
    def __init__(self,axil_offset=0,buf_size=system_buf_size,buf_offset=0,dma_buflen=26):
        self.axil = axilite(axil_offset)
        self.phy_buf = phy_buf(buf_offset,buf_size)
        self.bufsize = buf_size
        self.dma_bufsize = 2**dma_buflen
        self.ps_phy_addr = self.phy_buf.phy_addr
    def buf_write(self,raw_bytes,offset=0):
        return self.phy_buf.write(raw_bytes,offset)
    def buf_read(self,size,offset=0):
        return self.phy_buf.read(size,offset)
    def __mm2s(self,addr,size,timeout,sync):
        CR_ADDR = 0x0
        SR_ADDR = 0x4
        SA_ADDR = 0x18
        LEN_ADDR = 0x28
        for i in range(timeout):
            isIdle = getbit(self.axil.read32(SR_ADDR),0) or getbit(self.axil.read32(SR_ADDR),1) #halt or idle 
            if isIdle == 1:
                break
            else:
                time.sleep(0.001)
            if i == timeout-1:
                print('mm2s time out!')
                return 1
        oldCtrlVal=self.axil.read32(CR_ADDR)
        newCtrlVal=setbit(oldCtrlVal,0,1)
        self.axil.write32(newCtrlVal,CR_ADDR) #start
        self.axil.write64(addr,SA_ADDR) #Address
        self.axil.write32(size,LEN_ADDR) #Length
        newCtrlVal=setbit(newCtrlVal,0,0)
        self.axil.write32(newCtrlVal,CR_ADDR) #set start to 0
        if sync:
            for i in range(timeout):
                isIdle = getbit(self.axil.read32(SR_ADDR),0) or getbit(self.axil.read32(SR_ADDR),1) #halt or idle 
                if isIdle == 1:
                    break
                else:
                    time.sleep(0.001)
                if i == timeout-1:
                    print('mm2s time out!')
                    return 1        
        return 0
    def __s2mm(self,addr,size,timeout,sync):
        CR_ADDR = 0x30
        SR_ADDR = 0x34
        DA_ADDR = 0x48
        LEN_ADDR = 0x58
        for i in range(timeout):
            isIdle = getbit(self.axil.read32(SR_ADDR),0) or getbit(self.axil.read32(SR_ADDR),1) #halt or idle
            if isIdle == 1:
                break
            else:
                time.sleep(0.001)
            if i == timeout-1:
                print('s2mm time out!')
                return 1
        oldCtrlVal=self.axil.read32(CR_ADDR)
        newCtrlVal=setbit(oldCtrlVal,0,1)    
        self.axil.write32(newCtrlVal,CR_ADDR) #start
        self.axil.write64(addr,DA_ADDR) #Address
        self.axil.write32(size,LEN_ADDR)
        newCtrlVal=setbit(newCtrlVal,0,0)
        self.axil.write32(newCtrlVal,CR_ADDR) #set start to 0
        if sync:
            for i in range(timeout):
                isIdle = getbit(self.axil.read32(SR_ADDR),0) or getbit(self.axil.read32(SR_ADDR),1) #halt or idle
                if isIdle == 1:
                    break
                else:
                    time.sleep(0.001)
                if i == timeout-1:
                    print('s2mm time out!')
                    return 1
        return 0
    def mm2s(self,size,offset=0,timeout=2000,sync=False):
        if size+offset > self.bufsize:
            print("Trying to access beyond the allocated buffer area, exiting!")
            return 1
        #1.Data->Phy_mem in PS DDR
        #2.AXIDMA in PL <- Phy_mem in PS DDR (can be multiple)
        #    2 happens when 1 is completely done
        #This implementation works, but it's not the best performance,
        #    because 2 and 1 can be pipelined
        #If PS PL bandwidth is the bottleneck for the app,
        #    pingpong ram and pipeline can be used to optimize in the future
        for loc in range(0,size,self.dma_bufsize):
            curr_loc = self.ps_phy_addr + offset + loc
            size_bytes_to_go = min(self.dma_bufsize,size-loc)
            if self.__mm2s(curr_loc,size_bytes_to_go,timeout,sync):
                return 1
        return 0
    def s2mm(self,size,offset=0,timeout=2000,sync=False):
        if size+offset > self.bufsize:
            print("Trying to access beyond the allocated buffer area, exiting!")
            return 1
        for loc in range(0,size,self.dma_bufsize):
            curr_loc = self.ps_phy_addr + offset + loc
            size_bytes_to_come = min(self.dma_bufsize,size-loc)
            if self.__s2mm(curr_loc,size_bytes_to_come,timeout,sync):
                return 1
        return 0
    def clean(self):
        if self.phy_buf is not None:
            self.phy_buf.clean()
            self.phy_buf = None
        if self.axil is not None:
            self.axil.clean()
            self.axil = None

class axicdma:
    axil = None
    dma_bufsize = 2**23
    def __init__(self,axil_offset=0):
        self.axil = axilite(axil_offset)
    def __movedata(self,src_addr,dst_addr,size,timeout,sync):
        CR_ADDR = 0x0
        SR_ADDR = 0x4
        SA_ADDR = 0x18
        DA_ADDR = 0x20
        LEN_ADDR = 0x28
        for i in range(timeout):
            isIdle = getbit(self.axil.read32(SR_ADDR),1) #idle
            if isIdle == 1:
                break
            else:
                time.sleep(0.001)
            if i == timeout-1:
                print('CDMA time out!')
                return 1
        cr_value = self.axil.read32(CR_ADDR)
        new_cr_value = setbit(cr_value,12,0)
        self.axil.write32(new_cr_value,CR_ADDR) #control signal
        self.axil.write64(src_addr,SA_ADDR) #source address
        self.axil.write64(dst_addr,DA_ADDR) #destination address
        self.axil.write32(size,LEN_ADDR) #transfer size
        if sync:
            for i in range(timeout):
                isIdle = getbit(self.axil.read32(SR_ADDR),1) #idle
                if isIdle == 1:
                    break
                else:
                    time.sleep(0.001)
                if i == timeout-1:
                    print('CDMA time out!')
                    return 1
        sr_value = self.axil.read32(SR_ADDR)
        new_sr_value = setbit(sr_value,12,1)
        self.axil.write32(new_sr_value,SR_ADDR)
        return 0
    def movedata(self,src_addr,dst_addr,size,timeout=2000,sync=False):
        for loc in range(0,size,self.dma_bufsize):
            curr_loc_src = src_addr + loc
            curr_loc_dst = dst_addr + loc
            size_transfer = min(self.dma_bufsize,size-loc)
            if self.__movedata(curr_loc_src,curr_loc_dst,size_transfer,timeout,sync):
                return 1
        return 0
    def clean(self):
        if self.axil is not None:
            self.axil.clean()
            self.axil = None

class fpgamem:
    cdma = None
    phy_buf = None
    ps_base_addr = system_buf_addr
    pl_base_addr = 0
    def __init__(self,cdma_offset=0,ps_buf_offset=0,ps_buf_size=system_buf_size,fpgamem_mapbase=0):
        self.cdma = axicdma(cdma_offset)
        self.phy_buf = phy_buf(ps_buf_offset,ps_buf_size)
        self.ps_base_addr = system_buf_addr + ps_buf_offset
        self.pl_base_addr = fpgamem_mapbase
    def buf_write(self,raw_bytes,offset=0):
        return self.phy_buf.write(raw_bytes,offset)
    def buf_read(self,size,offset=0):
        return self.phy_buf.read(size,offset)
    def get(self,pl_offset=0,size=4096,sync=False):
        return self.cdma.movedata(self.pl_base_addr+pl_offset,self.ps_base_addr,size,sync)
    def put(self,pl_offset=0,size=4096,sync=False):
        return self.cdma.movedata(self.ps_base_addr,self.pl_base_addr+pl_offset,size,sync)
    def file2mem(self,f,pl_offset=0,size=-1):
        if isinstance(f,io.BufferedIOBase):
            fd=f
        elif isinstance(f,str):
            fd=open(f,'rb')
        else:
            print('ERROR: input file should be in binary format')
            return 1
        if size == -1:
            remain_size = 0x7ffff000 #size limit
        else:
            remain_size = size
        pl_addr=pl_offset
        while remain_size > 0:
            bytes_to_read = min(self.phy_buf.size,remain_size)
            remain_size -= bytes_to_read
            raw_bytes = fd.read(bytes_to_read)
            if len(raw_bytes) == 0:
                break
            self.buf_write(raw_bytes)
            self.put(pl_addr,len(raw_bytes),True)
            pl_addr+=bytes_to_read
        if isinstance(f,str):
            fd.close()
    def mem2file(self,f,pl_offset=0,size=4096):
        if isinstance(f,io.BufferedIOBase):
            fd=f
        elif isinstance(f,str):
            fd=open(f,'wb')
        else:
            print('ERROR: output file should be in binary format')
            return 1
        remain_size = size
        pl_addr=pl_offset
        while remain_size > 0:
            bytes_to_read = min(self.phy_buf.size,remain_size)
            remain_size -= bytes_to_read
            self.get(pl_addr,bytes_to_read,True)
            raw_bytes = self.buf_read(bytes_to_read)
            fd.write(raw_bytes)
            pl_addr+=bytes_to_read
            if len(raw_bytes) != bytes_to_read:
                break
        if isinstance(f,str):
            fd.close()
    def clean(self):
        if self.cdma is not None:
            self.cdma.clean()
            self.cdma = None
        if self.phy_buf is not None:
            self.phy_buf.clean()
            self.phy_buf = None
