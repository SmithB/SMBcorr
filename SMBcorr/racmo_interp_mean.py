#!/usr/bin/env python
u"""
racmo_interp_mean.py
Written by Tyler Sutterley (08/2020)
Interpolates the mean of downscaled RACMO products to spatial coordinates

CALLING SEQUENCE:
    python racmo_interp_mean.py --directory=<path> --version=3.0 \
        --product=SMB,PRECIP,RUNOFF --coordinate=[-39e4,-133e4],[-39e4,-133e4] \
        --date=2016.1,2018.1

COMMAND LINE OPTIONS:
    -D X, --directory=X: Working data directory
    --version=X: Downscaled RACMO Version
        1.0: RACMO2.3/XGRN11
        2.0: RACMO2.3p2/XGRN11
        3.0: RACMO2.3p2/FGRN055
    --product: RACMO product to calculate
        SMB: Surface Mass Balance
        PRECIP: Precipitation
        RUNOFF: Melt Water Runoff
        SNOWMELT: Snowmelt
        REFREEZE: Melt Water Refreeze
    --mean: Start and end year of mean (separated by commas)
    --coordinate=X: Polar Stereographic X and Y of point
    --date=X: Date to interpolate in year-decimal format
    --csv=X: Read dates and coordinates from a csv file
    --fill-value: Replace invalid values with fill value
        (default uses original fill values from data file)

PYTHON DEPENDENCIES:
    numpy: Scientific Computing Tools For Python
        https://numpy.org
        https://numpy.org/doc/stable/user/numpy-for-matlab-users.html
    scipy: Scientific Tools for Python
        https://docs.scipy.org/doc/
    netCDF4: Python interface to the netCDF C library
         https://unidata.github.io/netcdf4-python/netCDF4/index.html
    pyproj: Python interface to PROJ library
        https://pypi.org/project/pyproj/

UPDATE HISTORY:
    Updated 08/2020: attempt delaunay triangulation using different options
    Updated 09/2019: read subsets of DS1km netCDF4 file to save memory
    Written 09/2019
"""
from __future__ import print_function

import sys
import os
import re
import pyproj
import getopt
import netCDF4
import numpy as np
import scipy.spatial
import scipy.interpolate

#-- PURPOSE: find a valid Delaunay triangulation for coordinates x0 and y0
#-- http://www.qhull.org/html/qhull.htm#options
#-- Attempt 1: standard qhull options Qt Qbb Qc Qz
#-- Attempt 2: rescale and center the inputs with option QbB
#-- Attempt 3: joggle the inputs to find a triangulation with option QJ
#-- if no passing triangulations: exit with empty list
def find_valid_triangulation(x0,y0):
    #-- Attempt 1: try with standard options Qt Qbb Qc Qz
    #-- Qt: triangulated output, all facets will be simplicial
    #-- Qbb: scale last coordinate to [0,m] for Delaunay triangulations
    #-- Qc: keep coplanar points with nearest facet
    #-- Qz: add point-at-infinity to Delaunay triangulation

    #-- Attempt 2 in case of qhull error from Attempt 1 try Qt Qc QbB
    #-- Qt: triangulated output, all facets will be simplicial
    #-- Qc: keep coplanar points with nearest facet
    #-- QbB: scale input to unit cube centered at the origin

    #-- Attempt 3 in case of qhull error from Attempt 2 try QJ QbB
    #-- QJ: joggle input instead of merging facets
    #-- QbB: scale input to unit cube centered at the origin

    #-- try each set of qhull_options
    points = np.concatenate((x0[:,None],y0[:,None]),axis=1)
    for i,opt in enumerate(['Qt Qbb Qc Qz','Qt Qc QbB','QJ QbB']):
        try:
            triangle = scipy.spatial.Delaunay(points.data, qhull_options=opt)
        except scipy.spatial.qhull.QhullError:
            pass
        else:
            return (i+1,triangle)

    #-- if still errors: set triangle as an empty list
    triangle = []
    return (None,triangle)

#-- PURPOSE: read and interpolate downscaled RACMO products
def interpolate_racmo_mean(base_dir, EPSG, VERSION, tdec, X, Y,
    VARIABLE='SMB', RANGE=[], FILL_VALUE=None):

    #-- Full Directory Setup
    DIRECTORY = 'SMB1km_v{0}'.format(VERSION)

    #-- netcdf variable names
    input_products = {}
    input_products['SMB'] = 'SMB_rec'
    input_products['PRECIP'] = 'precip'
    input_products['RUNOFF'] = 'runoff'
    input_products['SNOWMELT'] = 'snowmelt'
    input_products['REFREEZE'] = 'refreeze'
    #-- version 1 was in separate files for each year
    if (VERSION == '1.0'):
        RACMO_MODEL = ['XGRN11','2.3']
        VARNAME = input_products[VARIABLE]
        SUBDIRECTORY = '{0}_v{1}'.format(VARNAME,VERSION)
        input_dir = os.path.join(base_dir, 'RACMO', DIRECTORY, SUBDIRECTORY)
    elif (VERSION == '2.0'):
        RACMO_MODEL = ['XGRN11','2.3p2']
        var = input_products[VARIABLE]
        VARNAME = var if VARIABLE in ('SMB','PRECIP') else '{0}corr'.format(var)
        input_dir = os.path.join(base_dir, 'RACMO', DIRECTORY)
    elif (VERSION == '3.0'):
        RACMO_MODEL = ['FGRN055','2.3p2']
        var = input_products[VARIABLE]
        VARNAME = var if (VARIABLE == 'SMB') else '{0}corr'.format(var)
        input_dir = os.path.join(base_dir, 'RACMO', DIRECTORY)

    #-- read mean from netCDF4 file
    arg = (RACMO_MODEL[0],RACMO_MODEL[1],VERSION,VARIABLE,RANGE[0],RANGE[1])
    mean_file = '{0}_RACMO{1}_DS1km_v{2}_{3}_Mean_{4:4d}-{5:4d}.nc'.format(*arg)
    with netCDF4.Dataset(os.path.join(input_dir,mean_file),'r') as fileID:
        MEAN = fileID[VARNAME][:,:].copy()

    #-- input cumulative netCDF4 file
    args = (RACMO_MODEL[0],RACMO_MODEL[1],VERSION,VARIABLE)
    input_file = '{0}_RACMO{1}_DS1km_v{2}_{3}_cumul.nc'.format(*args)

    #-- Open the RACMO NetCDF file for reading
    fileID = netCDF4.Dataset(os.path.join(input_dir,input_file), 'r')
    #-- input shape of RACMO data
    nt,ny,nx = fileID[VARNAME].shape
    #-- Get data from each netCDF variable and remove singleton dimensions
    d = {}
    #-- cell origins on the bottom right
    dx = np.abs(fileID.variables['x'][1]-fileID.variables['x'][0])
    dy = np.abs(fileID.variables['y'][1]-fileID.variables['y'][0])
    #-- x and y arrays at center of each cell
    d['x'] = fileID.variables['x'][:].copy() - dx/2.0
    d['y'] = fileID.variables['y'][:].copy() - dy/2.0
    #-- extract time (decimal years)
    d['TIME'] = fileID.variables['TIME'][:].copy()
    #-- mask object for interpolating data
    d['MASK'] = np.array(fileID.variables['MASK'][:],dtype=np.bool)
    i,j = np.nonzero(d['MASK'])

    #-- convert projection from input coordinates (EPSG) to model coordinates
    proj1 = pyproj.Proj("+init={0}".format(EPSG))
    proj2 = pyproj.Proj("+init=EPSG:{0:d}".format(3413))
    ix,iy = pyproj.transform(proj1, proj2, X, Y)
    #-- check that input points are within convex hull of valid model points
    xg,yg = np.meshgrid(d['x'],d['y'])
    v,triangle = find_valid_triangulation(xg[i,j],yg[i,j])
    #-- check where points are within the complex hull of the triangulation
    if v:
        interp_points = np.concatenate((ix[:,None],iy[:,None]),axis=1)
        valid = (triangle.find_simplex(interp_points) >= 0)
    else:
        #-- Check ix and iy against the bounds of x and y
        valid = (ix >= d['x'].min()) & (ix <= d['x'].max()) & \
            (iy >= d['y'].min()) & (iy <= d['y'].max())

    #-- output interpolated arrays of variable
    interp_var = np.zeros_like(tdec,dtype=np.float)
    #-- type designating algorithm used (1: interpolate, 2: backward, 3:forward)
    interp_type = np.zeros_like(tdec,dtype=np.uint8)
    #-- interpolation mask of invalid values
    interp_mask = np.zeros_like(tdec,dtype=np.bool)

    #-- find days that can be interpolated
    if np.any(valid):
        #-- indices of dates for interpolated days
        ind, = np.nonzero(valid)
        #-- create an interpolator for variable
        RGI=scipy.interpolate.RegularGridInterpolator((d['y'],d['x']),MEAN)
        #-- create an interpolator for input mask
        MI=scipy.interpolate.RegularGridInterpolator((d['y'],d['x']),d['MASK'])
        #-- interpolate to points
        dt = (tdec[ind] - d['TIME'][0])/(d['TIME'][1] - d['TIME'][0])
        interp_var[ind] = dt*RGI.__call__(np.c_[iy[ind],ix[ind]])
        interp_mask[ind] = MI.__call__(np.c_[iy[ind],ix[ind]])
        #-- set interpolation type (1: interpolated)
        interp_type[ind] = 1

    #-- replace fill value if specified
    if FILL_VALUE:
        ind, = np.nonzero(~interp_mask)
        interp_var[ind] = FILL_VALUE
        fv = FILL_VALUE
    else:
        fv = 0.0

    #-- close the NetCDF files
    fileID.close()

    #-- return the interpolated values
    return (interp_var,interp_type,fv)

#-- PURPOSE: interpolate RACMO products to a set of coordinates and times
#-- wrapper function to extract EPSG and print to terminal
def racmo_interp_mean(base_dir, VERSION, PRODUCT, RANGE=[],
    COORDINATES=None, DATES=None, CSV=None, FILL_VALUE=None):

    #-- this is the projection of the coordinates being interpolated into
    EPSG = "EPSG:{0:d}".format(3413)

    #-- read coordinates and dates from a csv file (X,Y,year decimal)
    if CSV:
        X,Y,tdec = np.loadtxt(CSV,delimiter=',').T
    else:
        #-- regular expression pattern for extracting x and y coordinates
        numerical_regex = '([-+]?(?:(?:\d*\.\d+)|(?:\d+\.?))(?:[Ee][+-]?\d+)?)'
        regex = re.compile('\[{0},{0}\]'.format(numerical_regex))
        #-- number of coordinates
        npts = len(regex.findall(COORDINATES))
        #-- x and y coordinates of interpolation points
        X = np.zeros((npts))
        Y = np.zeros((npts))
        for i,XY in enumerate(regex.findall(COORDINATES)):
            X[i],Y[i] = np.array(XY, dtype=np.float)
        #-- convert dates to ordinal days (count of days of the Common Era)
        tdec = np.array(DATES, dtype=np.float)

    #-- read and interpolate/extrapolate RACMO2.3 products
    vi,itype,fv = interpolate_racmo_mean(base_dir, EPSG, VERSION, PRODUCT,
        tdec, X, Y, RANGE=RANGE, FILL_VALUE=FILL_VALUE)
    interpolate_types = ['invalid','interpolated','backward','forward']
    for v,t in zip(vi,itype):
        print(v,interpolate_types[t])

#-- PURPOSE: help module to describe the optional input parameters
def usage():
    print('\nHelp: {}'.format(os.path.basename(sys.argv[0])))
    print(' -D X, --directory=X\tWorking data directory')
    print(' --version=X\t\tDownscaled RACMO Version')
    print('\t1.0: RACMO2.3/XGRN11')
    print('\t2.0: RACMO2.3p2/XGRN11')
    print('\t3.0: RACMO2.3p2/FGRN055')
    print(' --product:\t\tRACMO product to calculate')
    print('\tSMB: Surface Mass Balance')
    print('\tPRECIP: Precipitation')
    print('\tRUNOFF: Melt Water Runoff')
    print('\tSNOWMELT: Snowmelt')
    print('\tREFREEZE: Melt Water Refreeze')
    print(' --mean:\t\tStart and end year of mean (separated by commas)')
    print(' --coordinate=X\t\tPolar Stereographic X and Y of point')
    print(' --date=X\t\tDates to interpolate in year-decimal format')
    print(' --csv=X\t\tRead dates and coordinates from a csv file')
    print(' --fill-value\t\tReplace invalid values with fill value\n')

#-- Main program that calls racmo_interp_mean()
def main():
    #-- Read the system arguments listed after the program
    long_options = ['help','directory=','version=','product=','mean=',
        'coordinate=','date=','csv=','fill-value=']
    optlist,arglist = getopt.getopt(sys.argv[1:], 'hD:', long_options)

    #-- data directory
    base_dir = os.getcwd()
    #-- Downscaled version
    VERSION = '3.0'
    #-- Products to calculate cumulative
    PRODUCTS = ['SMB']
    #-- mean range
    RANGE = [1961,1990]
    #-- coordinates and times to run
    COORDINATES = None
    DATES = None
    #-- read coordinates and dates from csv file
    CSV = None
    #-- invalid value (default is nan)
    FILL_VALUE = np.nan
    #-- extract parameters
    for opt, arg in optlist:
        if opt in ('-h','--help'):
            usage()
            sys.exit()
        elif opt in ("-D","--directory"):
            base_dir = os.path.expanduser(arg)
        elif opt in ("--version"):
            VERSION = arg
        elif opt in ("--product"):
            PRODUCTS = arg.split(',')
        elif opt in ("--mean"):
            RANGE = np.array(arg.split(','),dtype=np.int)
        elif opt in ("--coordinate"):
            COORDINATES = arg
        elif opt in ("--date"):
            DATES = arg.split(',')
        elif opt in ("--csv"):
            CSV = os.path.expanduser(arg)
        elif opt in ("--fill-value"):
            FILL_VALUE = eval(arg)

    #-- data product longnames
    longname = {}
    longname['SMB'] = 'Cumulative Surface Mass Balance Anomalies'
    longname['PRECIP'] = 'Cumulative Precipitation Anomalies'
    longname['RUNOFF'] = 'Cumulative Runoff Anomalies'
    longname['SNOWMELT'] = 'Cumulative Snowmelt Anomalies'
    longname['REFREEZE'] = 'Cumulative Melt Water Refreeze Anomalies'

    #-- for each product
    for p in PRODUCTS:
        #-- check that product was entered correctly
        if p not in longname.keys():
            raise IOError('{0} not in valid RACMO products'.format(p))
        #-- run program with parameters
        racmo_interp_mean(base_dir,VERSION,p,RANGE=RANGE,COORDINATES=COORDINATES,
            DATES=DATES,CSV=CSV,FILL_VALUE=FILL_VALUE)

#-- run main program
if __name__ == '__main__':
    main()
