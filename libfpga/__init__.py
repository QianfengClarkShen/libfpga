import platform
arch=platform.processor()
if arch == 'x86_64':
    print('Detected %s architecture, using XDMA as backend. Please make sure the XDMA driver has been properlly installed and enabled' % arch)
    from libfpga.xdma import *
elif arch == 'aarch64':
    print('Detected %s architecture, using u-dma-buf (https://github.com/ikwzm/udmabuf) as backend. Please make sure the u-dma-buf driver has been properlly installed and enabled, and a buffer called /dev/phy_buf has been created using the driver' % arch)
    from libfpga.mpsoc import *
else:
    print('Architecutre %s is not supported' % arch)
