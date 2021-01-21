import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="libfpga",
    version="0.0.2",
    author="Qianfeng (Clark) Shen",
    author_email="qianfeng.shen@gmail.com",
    description="Python3 library for operating DMA and register manipualtion on Xilinx FPGAs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/QianfengClarkShen/libfpga",
    packages=['libfpga'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires='>=3.5.0',
)
