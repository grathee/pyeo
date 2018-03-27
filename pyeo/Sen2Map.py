# -*- coding: utf-8 -*-
"""
Created on Sat Mar 24 12:11:00 2018

@author: Heiko Balzter
"""

#############################################################################
# read all Sentinel-2 band geotiffs in a directory and a shape file
#   and make RGB quicklook maps at different scales
# written for Python 3.6.4
#############################################################################

# TODO for John IMPORTANT:
# When you start the IPython Kernel, type in:
#   %matplotlib
# This will launch a graphical user interface (GUI) loop

# import geojson as gj
# from geojson import Polygon
# import matplotlib
import cartopy
import cartopy.crs as ccrs
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature, BORDERS
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
# from geospatial_learn import geodata, learning
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
# import mpl_toolkits
# from mpl_toolkits.basemap import Basemap, shiftgrid, cm
import numpy as np
import os, sys
from os import listdir
from os.path import isfile, isdir, join
from osgeo import gdal, gdalnumeric, ogr, osr

gdal.UseExceptions()
import pylab
from skimage import io

io.use_plugin('matplotlib')
from scipy import stats, optimize, ndimage

# The pyplot interface provides 4 commands that are useful for interactive control.
# plt.isinteractive() returns the interactive setting True|False
# plt.ion() turns interactive mode on
# plt.ioff() turns interactive mode off
# plt.draw() forces a figure redraw

#############################################################################
# OPTIONS
#############################################################################
# wd = '/scratch/clcr/shared/py/' # working directory on Linux HPC
wd = '/home/heiko/linuxpy/mexico/'  # working directory on Linux Virtual Box
datadir = wd + 'data/'  # directory of Sentinel data files
# the shapefile resides in wd
shapefile = 'Sitios_Poly.shp'
# define the Sentinel 2 scene ID (this is the directory name)
scenedir = 'S2A_MSIL1C_20170413T173821_N0204_R012_T13QDB_20170413T173823.SAFE'
tiffdir = datadir + scenedir + '/tiff/'  # directory where geotiffs are stored
bands = [5, 4, 3]  # band selection for RGB


#############################################################################
# FUNCTION DECLARATIONS
#############################################################################
def func(t, A, K, C):
    return A * np.exp(-K * t) + C


def fit_exp_nonlinear(t, y):
    opt_parms, parm_cov = optimize.curve_fit(func, t, y, maxfev=15000)
    A, K, C = opt_parms
    return A, K, C


# define functions to read/write floating point numbers from/to a text file
def read_floats(filename):
    with open(filename) as f:
        return [float(x) for x in f]
    f.close()


def write_floats(data, filename):
    file = open(filename, 'w')
    for item in data:
        file.write("%f\n" % item)
    file.close()


def get_gridlines(x0, x1, y0, y1, nticks):
    '''
    make neat gridline labels for map projections
        x0, x1 = minimum and maximum x positions in map projection coordinates
        y0, y1 = minimum and maximum y positions in map projection coordinates
        nticks = number of ticks / gridlines in x direction
        returns two numpy arrays with x and y tick positions
    '''
    # make sure gridline positions have min 2 digits
    ndigits = len(str(abs(x0)).split('.')[0])  # number of digits before the decimal point
    xx0 = x0
    xfactor = 1  # how many time do we need to multiply by 10
    while ndigits < 2:
        xx0 = xx0 * 10
        xfactor = xfactor * 10
        ndigits = len(str(abs(xx0)).split('.')[0])  # number of digits before the decimal point
        if xfactor > 100000:
            print('\nError in XFactor while loop!')
            break
    x0 = round(x0 * xfactor, 0) / xfactor
    x1 = round(x1 * xfactor, 0) / xfactor
    y0 = round(y0 * xfactor, 0) / xfactor
    y1 = round(y1 * xfactor, 0) / xfactor
    # make sure gridline positions have max 3 digits
    ndigits = len(str(abs(x0)).split('.')[0])  # number of digits before the decimal point
    xx0 = x0
    xfactor = 1  # how many time do we need to divide by 10
    while ndigits > 3:
        xx0 = xx0 / 10
        xfactor = xfactor * 10
        ndigits = len(str(abs(xx0)).split('.')[0])  # number of digits before the decimal point
        if xfactor > 100000:
            print('\nError in XFactor while loop!')
            break
    x0 = round(x0 / xfactor, 0) * xfactor
    x1 = round(x1 / xfactor, 0) * xfactor
    y0 = round(y0 / xfactor, 0) * xfactor
    y1 = round(y1 / xfactor, 0) * xfactor
    # carry on
    dx = (x1 - x0) / nticks
    dy = (y1 - y0) / nticks
    xticks = np.arange(x0, x1 + dx, dx)
    yticks = np.arange(y0, y1 + dy, dy)
    return xticks, yticks


# plot a scale bar with 4 subdivisions on the left side of the map
def scale_bar_left(ax, bars=4, length=None, location=(0.1, 0.05), linewidth=3, col='black'):
    """
    ax is the axes to draw the scalebar on.
    bars is the number of subdivisions of the bar (black and white chunks)
    length is the length of the scalebar in km.
    location is left side of the scalebar in axis coordinates.
    (ie. 0 is the left side of the plot)
    linewidth is the thickness of the scalebar.
    color is the color of the scale bar
    """
    # Get the limits of the axis in lat long
    llx0, llx1, lly0, lly1 = ax.get_extent(ccrs.PlateCarree())
    # Make tmc aligned to the left of the map,
    # vertically at scale bar location
    sbllx = llx0 + (llx1 - llx0) * location[0]
    sblly = lly0 + (lly1 - lly0) * location[1]
    tmc = ccrs.TransverseMercator(sbllx, sblly)
    # Get the extent of the plotted area in coordinates in metres
    x0, x1, y0, y1 = ax.get_extent(tmc)
    # Turn the specified scalebar location into coordinates in metres
    sbx = x0 + (x1 - x0) * location[0]
    sby = y0 + (y1 - y0) * location[1]

    # Calculate a scale bar length if none has been given
    # (Theres probably a more pythonic way of rounding the number but this works)
    if not length:
        length = (x1 - x0) / 5000  # in km
        ndim = int(np.floor(np.log10(length)))  # number of digits in number
        length = round(length, -ndim)  # round to 1sf

        # Returns numbers starting with the list
        def scale_number(x):
            if str(x)[0] in ['1', '2', '5']:
                return int(x)
            else:
                return scale_number(x - 10 ** ndim)

        length = scale_number(length)

    # Generate the x coordinate for the ends of the scalebar
    bar_xs = [sbx, sbx + length * 1000 / bars]
    # Plot the scalebar chunks
    barcol = 'white'
    for i in range(0, bars):
        # plot the chunk
        ax.plot(bar_xs, [sby, sby], transform=tmc, color=barcol, linewidth=linewidth)
        # alternate the colour
        if barcol == 'white':
            barcol = 'dimgrey'
        else:
            barcol = 'white'
        # Generate the x coordinate for the number
        bar_xt = sbx + i * length * 1000 / bars
        # Plot the scalebar label for that chunk
        ax.text(bar_xt, sby, str(round(i * length / bars)), transform=tmc,
                horizontalalignment='center', verticalalignment='bottom',
                color=col)
        # work out the position of the next chunk of the bar
        bar_xs[0] = bar_xs[1]
        bar_xs[1] = bar_xs[1] + length * 1000 / bars
    # Generate the x coordinate for the last number
    bar_xt = sbx + length * 1000
    # Plot the last scalebar label
    ax.text(bar_xt, sby, str(round(length)), transform=tmc,
            horizontalalignment='center', verticalalignment='bottom',
            color=col)
    # Plot the unit label below the bar
    bar_xt = sbx + length * 1000 / 2
    bar_yt = y0 + (y1 - y0) * (location[1] / 4)
    ax.text(bar_xt, bar_yt, 'km', transform=tmc, horizontalalignment='center',
            verticalalignment='bottom', color=col)


# plot a scale bar on the map
def scale_bar(ax, length=None, location=(0.5, 0.05), linewidth=3, col='black'):
    """
    ax is the axes to draw the scalebar on.
    length is the length of the scalebar in km.
    location is center of the scalebar in axis coordinates.
    (ie. 0.5 is the middle of the plot)
    linewidth is the thickness of the scalebar.
    color is the color of the scale bar
    """
    # Get the limits of the axis in lat long
    llx0, llx1, lly0, lly1 = ax.get_extent(ccrs.PlateCarree())
    # Make tmc horizontally centred on the middle of the map,
    # vertically at scale bar location
    sbllx = (llx1 + llx0) / 2
    sblly = lly0 + (lly1 - lly0) * location[1]
    tmc = ccrs.TransverseMercator(sbllx, sblly)
    # Get the extent of the plotted area in coordinates in metres
    x0, x1, y0, y1 = ax.get_extent(tmc)
    # Turn the specified scalebar location into coordinates in metres
    sbx = x0 + (x1 - x0) * location[0]
    sby = y0 + (y1 - y0) * location[1]

    # Calculate a scale bar length if none has been given
    # (Theres probably a more pythonic way of rounding the number but this works)
    if not length:
        length = (x1 - x0) / 5000  # in km
        ndim = int(np.floor(np.log10(length)))  # number of digits in number
        length = round(length, -ndim)  # round to 1sf

        # Returns numbers starting with the list
        def scale_number(x):
            if str(x)[0] in ['1', '2', '5']:
                return int(x)
            else:
                return scale_number(x - 10 ** ndim)

        length = scale_number(length)

    # Generate the x coordinate for the ends of the scalebar
    bar_xs = [sbx - length * 500, sbx + length * 500]
    # Plot the scalebar
    ax.plot(bar_xs, [sby, sby], transform=tmc, color=col, linewidth=linewidth)
    # Plot the scalebar label
    ax.text(sbx, sby, str(length) + ' km', transform=tmc,
            horizontalalignment='center', verticalalignment='bottom',
            color=col)


# function to convert coordinates
def convertXY(xy_source, inproj, outproj):
    shape = xy_source[0, :, :].shape
    size = xy_source[0, :, :].size
    # the ct object takes and returns pairs of x,y, not 2d grids
    # so the the grid needs to be reshaped (flattened) and back.
    ct = osr.CoordinateTransformation(inproj, outproj)
    xy_target = np.array(ct.TransformPoints(xy_source.reshape(2, size).T))
    xx = xy_target[:, 0].reshape(shape)
    yy = xy_target[:, 1].reshape(shape)
    return xx, yy


# define a plotting function to make a map, masking out all values < -99
def do_map(image, lat, lon, parallels, meridians, file, title, zlim):
    # image = 2D array
    # lat, lon = arrays of latitude / longitude coordinates (same dimensions as image)
    # parallels = vector of parralels to be drawn, e.g. np.arange(-90., 99., 30.)
    # meridians = vector of meridians, e.g. np.arange(-180., 180., 60.)
    # file = filename including path
    # title = title string for map
    # zlim = min and max values for color scale [zmin,zmax]
    masked_image = ma.masked_less(image, -99)
    # make the figure
    fig = plt.figure()
    ax = fig.add_axes([0.05, 0.05, 0.9, 0.9])
    # if coastlines not used, set resolution to None to skip continent processing (this speeds things up a bit)
    mymap = Basemap(projection='kav7', lon_0=0, resolution='c')
    # color background of map projection region. Missing values over land will show up this color.
    mymap.drawmapboundary(fill_color="#7777ff")
    # mymap.fillcontinents(color='slategrey',lake_color='royalblue', alpha=1)
    mymap.drawlsmask(land_color="chocolate", ocean_color="cornflowerblue", resolution='i')
    # land_color = "#ddaa66", ocean_color="#7777ff", resolution = 'l')
    # mymap.bluemarble()
    im1 = mymap.pcolormesh(lon, lat, masked_image, shading='flat', cmap=plt.cm.jet, vmin=zlim[0], vmax=zlim[1],
                           latlon=True)
    mymap.drawparallels(parallels, linewidth=0.5)
    mymap.drawmeridians(meridians, linewidth=0.5)
    cb = mymap.colorbar(im1, "bottom", size="5%", pad="2%")
    ax.set_title(title)
    mymap.drawcoastlines(linewidth=0.5, color='white')
    mymap.drawcountries(linewidth=0.5, color='white'), pylab.savefig(file, figsize=(figsizex, figsizey), dpi=300)
    fig.clf()


# This function will convert the rasterized clipper shapefile to a mask for use within GDAL.
def imageToArray(i):
    """
    Converts a Python Imaging Library array to a
    gdalnumeric image.
    """
    a = gdalnumeric.fromstring(i.tostring(), 'b')
    a.shape = i.im.size[1], i.im.size[0]
    return a


def world2Pixel(geoMatrix, x, y):
    """
    Uses a gdal geomatrix (gdal.GetGeoTransform()) to calculate
    the pixel location of a geospatial coordinate
    """
    ulX = geoMatrix[0]
    ulY = geoMatrix[3]
    xDist = geoMatrix[1]
    yDist = geoMatrix[5]
    rtnX = geoMatrix[2]
    rtnY = geoMatrix[4]
    pixel = int((x - ulX) / xDist)
    line = int((ulY - y) / xDist)
    return (pixel, line)


def transformxy(s_srs, t_srs, xcoord, ycoord):
    """
    Transforms a point coordinate x,y from a source reference system (s_srs)
    to a target reference system (t_srs)
    """
    geom = ogr.Geometry(ogr.wkbPoint)
    geom.SetPoint_2D(0, xcoord, ycoord)
    geom.AssignSpatialReference(s_srs)
    geom.TransformTo(t_srs)
    return geom.GetPoint_2D()


def projectshape(inshp, outshp, t_srs):
    """
    Reprojects an ESRI shapefile from its source reference system
    to a target reference system (e.g. t_srs = 4326)
    filenames must include the full directory paths
    requires:
        from osgeo import ogr, osr
        import os
    """
    # for testing:
    #    inshp = wd+shapefile
    #    outshp = wd+shapefile[:-4]+"_4326.shp"
    #    t_srs = 4326

    driver = ogr.GetDriverByName('ESRI Shapefile')  # get shapefile driver
    infile = driver.Open(inshp, 0)
    if infile is None:
        print('Could not open ' + inshp)
        sys.exit(1)  # exit with an error code
    inLayer = infile.GetLayer()  # get input layer
    inSpatialRef = inLayer.GetSpatialRef()  # get source spatial reference system
    # or input SpatialReference manually here
    #   inSpatialRef = osr.SpatialReference()
    #   inSpatialRef.ImportFromEPSG(2927)
    outSpatialRef = osr.SpatialReference()
    outSpatialRef.ImportFromEPSG(t_srs)
    # create the CoordinateTransformation
    coordTrans = osr.CoordinateTransformation(inSpatialRef, outSpatialRef)
    # create the output layer
    if os.path.exists(outshp):
        driver.DeleteDataSource(outshp)
    outDataSet = driver.CreateDataSource(outshp)
    outLayer = outDataSet.CreateLayer("basemap_" + str(t_srs), geom_type=ogr.wkbMultiPolygon)
    # add fields
    inLayerDefn = inLayer.GetLayerDefn()
    for i in range(0, inLayerDefn.GetFieldCount()):
        fieldDefn = inLayerDefn.GetFieldDefn(i)
        outLayer.CreateField(fieldDefn)
    # get the output layer's feature definition
    outLayerDefn = outLayer.GetLayerDefn()
    # loop through the input features
    inFeature = inLayer.GetNextFeature()
    while inFeature:
        # get the input geometry
        geom = inFeature.GetGeometryRef()
        # reproject the geometry
        geom.Transform(coordTrans)
        # create a new feature
        outFeature = ogr.Feature(outLayerDefn)
        # set the geometry and attribute
        outFeature.SetGeometry(geom)
        for i in range(0, outLayerDefn.GetFieldCount()):
            outFeature.SetField(outLayerDefn.GetFieldDefn(i).GetNameRef(), inFeature.GetField(i))
        # add the feature to the shapefile
        outLayer.CreateFeature(outFeature)
        # dereference the features and get the next input feature
        outFeature = None
        inFeature = inLayer.GetNextFeature()
    # Save and close the shapefiles
    inDataSet = None
    outDataSet = None
    # Try to open the output file to check it worked
    outfile = driver.Open(outshp, 0)
    if outfile is None:
        print('Failed to create ' + outshp)
        sys.exit(1)  # exit with an error code
    else:
        print('Reprojection of shapefile seems to have worked.')
    return None


def OpenArray(array, prototype_ds=None, xoff=0, yoff=0):
    #  this is basically an overloaded version of the gdal_array.OpenArray passing in xoff, yoff explicitly
    #  so we can pass these params off to CopyDatasetInfo
    ds = gdal.Open(gdalnumeric.GetArrayFilename(array))

    if ds is not None and prototype_ds is not None:
        if type(prototype_ds).__name__ == 'str':
            prototype_ds = gdal.Open(prototype_ds)
        if prototype_ds is not None:
            gdalnumeric.CopyDatasetInfo(prototype_ds, ds, xoff=xoff, yoff=yoff)
    return ds


def histogram(a, bins=range(0, 256)):
    """
    Histogram function for multi-dimensional array.
    a = array
    bins = range of numbers to match
    """
    fa = a.flat
    n = gdalnumeric.searchsorted(gdalnumeric.sort(fa), bins)
    n = gdalnumeric.concatenate([n, [len(fa)]])
    hist = n[1:] - n[:-1]
    return hist


def stretch(im, nbins=256, nozero=True):
    """
    Performs a histogram stretch on an ndarray image.
    """
    # modified from http://www.janeriksolem.net/2009/06/histogram-equalization-with-python-and.html

    # ignore zeroes
    if nozero:
        im2 = im[np.not_equal(im, 0)]
    else:
        im2 = im
    # get image histogram
    image_histogram, bins = np.histogram(im2.flatten(), nbins, normed=True)
    cdf = image_histogram.cumsum()  # cumulative distribution function
    cdf = 255 * cdf / cdf[-1]  # normalize
    # use linear interpolation of cdf to find new pixel values
    image_equalized = np.interp(im.flatten(), bins[:-1], cdf)
    return image_equalized.reshape(im.shape), cdf


def read_sen2_rgb(rgbfiles, enhance=True):
    '''
    reads in 3 separate geotiff files as R G and B channels
    rgbfiles: list of three filenames including directory structure
    enhance = True: applies histogram stretching (optional)
    returns a data frame scaled to unsigned 8 bit integer values
    '''
    # make array of 8-bit unsigned integers to be memory efficient
    # open the first file with GDAL to get dimensions
    ds = gdal.Open(rgbfiles[0])
    data = ds.ReadAsArray()
    rgbdata = np.zeros([len(bands), data.shape[0], data.shape[1]], \
                       dtype=np.uint8)

    for i, thisfile in enumerate(rgbfiles):
        print('Reading data from ' + thisfile)

        # open the file with GDAL
        ds = gdal.Open(thisfile)
        data = ds.ReadAsArray()

        # only process single-band files, these have not got 3 bands
        if data.shape[0] > 3:
            # histogram stretching and keeping the values in
            #   the RGB data array as 8 bit unsigned integers
            rgbdata[i, :, :] = np.uint8(stretch(data)[0])
    return rgbdata


def map_it(rgbdata, tifproj, mapextent, shapefile, plotfile='map.jpg',
           plottitle='', figsizex=10, figsizey=10):
    '''
    standard map making function that saves a jpeg file of the output
    and visualises it on screen
    rgbdata = numpy array of the red, green and blue channels, made by read_sen2rgb
    tifproj = map projection of the tiff files from which the rgbdata originate
    mapextent = extent of the map in map coordinates
    shapefile = shapefile name to be plotted on top of the map
    shpproj = map projection of the shapefile
    plotfile = output filename for the map plot
    plottitle = text to be written above the map
    figsizex = width of the figure in inches
    figsizey = height of the figure in inches
    '''
    # get shapefile projection from the file
    # get driver to read a shapefile and open it
    driver = ogr.GetDriverByName('ESRI Shapefile')
    dataSource = driver.Open(shapefile, 0)
    if dataSource is None:
        print('Could not open ' + shapefile)
        sys.exit(1)  # exit with an error code
    # get the layer from the shapefile
    layer = dataSource.GetLayer()
    # get the projection information and convert to wkt
    ####################################
    # most certain that we do not need all this
    ####################################
    projsr = layer.GetSpatialRef()
    projwkt = projsr.ExportToWkt()
    projosr = osr.SpatialReference()
    projosr.ImportFromWkt(projwkt)
    ####################################
    # convert wkt projection to Cartopy projection
    projcs = projosr.GetAuthorityCode('PROJCS')
    shapeproj = ccrs.epsg(projcs)

    # make the figure and the axes
    subplot_kw = dict(projection=tifproj)
    fig, ax = plt.subplots(figsize=(figsizex, figsizey),
                           subplot_kw=subplot_kw)

    # set a margin around the data
    ax.set_xmargin(0.05)
    ax.set_ymargin(0.10)

    # add a background image for rendering
    ax.stock_img()

    # show the data from the geotiff RGB image
    img = ax.imshow(rgbdata[:3, :, :].transpose((1, 2, 0)),
                    extent=extent, origin='upper')

    # read shapefile and plot it onto the tiff image map
    shape_feature = ShapelyFeature(Reader(shapefile).geometries(),
                                   crs=shapeproj, edgecolor='yellow',
                                   facecolor='none')
    ax.add_feature(shape_feature)

    # add a title
    plt.title(plottitle)

    # set map extent
    ax.set_extent(mapextent, tifproj)

    # add coastlines
    ax.coastlines(resolution='10m', color='navy', linewidth=1)

    # add lakes and rivers
    ax.add_feature(cartopy.feature.LAKES, alpha=0.5)
    ax.add_feature(cartopy.feature.RIVERS)

    # add borders
    BORDERS.scale = '10m'
    ax.add_feature(BORDERS, color='red')

    # format the gridline positions nicely
    xticks, yticks = get_gridlines(mapextent[0], mapextent[1],
                                   mapextent[2], mapextent[3],
                                   nticks=10)

    # add gridlines
    gl = ax.gridlines(crs=tifproj, xlocs=xticks, ylocs=yticks,
                      linestyle='--', color='grey', alpha=1, linewidth=1)

    # add ticks
    ax.set_xticks(xticks, crs=tifproj)
    ax.set_yticks(yticks, crs=tifproj)

    # stagger x gridline / tick labels
    labels = ax.set_xticklabels(xticks)
    for i, label in enumerate(labels):
        label.set_y(label.get_position()[1] - (i % 2) * 0.075)

    # add scale bar
    scale_bar_left(ax, bars=4, length=40, col='dimgrey')

    # show the map
    plt.show()

    # save it to a file
    plt.savefig(plotfile)


#############################################################################
# MAIN
#############################################################################

# set working directory
os.chdir(wd)

###################################################
# make plots directory for outputs
###################################################

# make a 'plots' directory (if it does not exist yet) for map output files
plotdir = wd + 'plots_' + shapefile.split(".")[0] + "/"
if not os.path.exists(plotdir):
    print("Creating directory: ", plotdir)
    os.mkdir(plotdir)

###################################################
# TODO make geotiff files or use original jpeg files
###################################################





###################################################
# get names of all geotiff files
###################################################

# change working directory
os.chdir(tiffdir)

# get list of all geotiff filenames
allfiles = sorted([f for f in os.listdir(tiffdir) if f.endswith('.tif')])
nfiles = len(allfiles)
print('\nProcessing %d Geotiff files:' % nfiles)
for thisfile in allfiles:
    print(thisfile)
print('\n\n')

###################################################
# read and plot the selected RGB bands / geotiffs onto a map
###################################################

# identify the filenames of the geotiff files for RGB map display
rgbfiles = []
for i in bands:
    rgbfiles.append(allfiles[i - 1])
for thisfile in rgbfiles:
    print(thisfile)
print('\n\n')

# open the first tiff file with GDAL to get file dimensions
thisfile = allfiles[0]
ds = gdal.Open(thisfile)
data = ds.ReadAsArray()

# get the projection information and convert to wkt
gt = ds.GetGeoTransform()
proj = ds.GetProjection()
inproj = osr.SpatialReference()
inproj.ImportFromWkt(proj)
print(inproj)

# convert wkt projection to Cartopy projection
projcs = inproj.GetAuthorityCode('PROJCS')
projection = ccrs.epsg(projcs)
print(projection)

# get the extent of the image
extent = (gt[0], gt[0] + ds.RasterXSize * gt[1],
          gt[3] + ds.RasterYSize * gt[5], gt[3])

# read in the three geotiff files
rgbdata = read_sen2_rgb(rgbfiles)

#######################################
# make a plot of the tiff file in the image projection
#######################################
plotfile = 'map1.jpg'
mapextent = extent
title = 'Sentinel 2 RGB image'
map_it(rgbdata, projection, mapextent, wd + shapefile,
       plotdir + plotfile,
       plottitle='Sentinel 2 RGB Quicklook',
       figsizex=10, figsizey=10)

plotfile = 'map2.jpg'
# need to unpack the tuple 'extent' and create a new tuple 'mapextent'
mapextent = (extent[0] - (extent[1] - extent[0]) * 0.5,
             extent[1] + (extent[1] - extent[0]) * 0.5,
             extent[2] - (extent[3] - extent[2]) * 0.5,
             extent[3] + (extent[3] - extent[2]) * 0.5)
title = 'Sentinel 2 zoom out'
map_it(rgbdata, projection, mapextent, wd + shapefile,
       plotdir + plotfile,
       plottitle='Sentinel 2 RGB Quicklook',
       figsizex=10, figsizey=10)

plotfile = 'map3.jpg'
# need to unpack the tuple 'extent' and create a new tuple 'mapextent'
# zoom in to the upper right corner, for example
mapextent = (extent[0] + (extent[1] - extent[0]) * 0.5,
             extent[1],
             extent[2] + (extent[3] - extent[2]) * 0.5,
             extent[3])
title = 'Sentinel 2 zoom in'
map_it(rgbdata, projection, mapextent, wd + shapefile,
       plotdir + plotfile,
       plottitle='Sentinel 2 RGB Quicklook',
       figsizex=10, figsizey=10)

########################
#
# TODO need to improve the colour of the scale bar on different background colours
# TODO or even better, plot the scale bar below the map outside of its boundaries
#
#
########################