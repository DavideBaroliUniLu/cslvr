import inspect
import os
import sys
from tifffile           import TiffFile
from numpy              import array, sqrt, shape, arange, meshgrid, loadtxt, \
                               gradient
from scipy.io           import loadmat, netcdf_file
from scipy.interpolate  import griddata
from pyproj             import Proj, transform
from cslvr.io           import print_text

class DataFactory(object):

  color = '229'
  global home 
  filename = inspect.getframeinfo(inspect.currentframe()).filename
  home     = os.path.dirname(os.path.abspath(filename)) + '/../data'
 
  @staticmethod 
  def print_dim(rg):
  
    for i in rg.variables.keys():
    
      dim = " ".join(rg.variables[i].dimensions)
      print i + "\n dimensons: " + dim
      
      if dim != "":
        print " Length of time: %d \n" % (len(rg.variables[i]), )
      else:
        print "\n"
  
  
  @staticmethod
  def get_ant_measures(res = 900):
    
    s    = "::: getting Antarctica measures data from DataFactory :::"
    print_text(s, DataFactory.color)

    global home
 
    if res == 900:
      direc    = home + '/antarctica/measures/antarctica_ice_velocity_900m.nc' 
    elif res == 450:
      direc    = home + '/antarctica/measures/antarctica_ice_velocity_450m.nc' 
    else:
      print "get_ant_measures() 'res' arg must be either 900 or 450"
      exit(0)

    data     = netcdf_file(direc, mode = 'r')
    vara     = dict()
  
    # retrieve data :
    vx   = array(data.variables['vx'][:])
    vy   = array(data.variables['vy'][:])
    err  = array(data.variables['err'][:])
    mask = (vx != 0.0).astype('i')
    
    names = ['vx', 'vy', 'v_err', 'mask']
    ftns  = [ vx,   vy,   err,     mask ]
    
    for n in names:
      print_text('      Measures : %-*s key : "%s" '%(30,n,n), '230')
    
    # extents of domain :
    nx,ny =  shape(vx)
    dx    =  res
    west  = -2800000.0
    east  =  west + nx*dx
    north =  2800000.0
    south =  north - ny*dx

    #projection info :
    proj   = 'stere'
    lat_0  = '-90'
    lat_ts = '-71'
    lon_0  = '0'
    
    # create projection :
    txt  =   " +proj="   + proj \
           + " +lat_0="  + lat_0 \
           + " +lat_ts=" + lat_ts \
           + " +lon_0="  + lon_0 \
           + " +k=1 +x_0=0 +y_0=0 +no_defs +a=6378137 +rf=298.257223563" \
           + " +towgs84=0.000,0.000,0.000 +to_meter=1"
    p    = Proj(txt)
    
    # save the data in matlab format :
    vara['pyproj_Proj']       = p
    vara['map_western_edge']  = west 
    vara['map_eastern_edge']  = east 
    vara['map_southern_edge'] = south 
    vara['map_northern_edge'] = north
    vara['nx']                = nx
    vara['ny']                = ny
    
    # save the data in matlab format :
    vara['dataset']   = 'measures'
    vara['continent'] = 'antarctica'
    for n, f in zip(names, ftns):
      vara[n] = f[::-1, :]
    return vara
  
  
  @staticmethod
  def get_gre_measures():
    
    s    = "::: getting Greenland measures data from DataFactory :::"
    print_text(s, DataFactory.color)
    
    global home
    
    direc    = home + '/greenland/measures/greenland_vel_mosaic500_2008_2009_' 
    files    = ['mask', 'vx', 'vy', 'ex', 'ey']
    vara     = dict()
    
    d    = TiffFile(direc + 'vx.tif')
    mask = (d.asarray() != -2e9).astype('i')
    
    ftns = [mask]
    for n in files[1:]:
      data    = TiffFile(direc + n + '.tif')
      ftns.append(data.asarray())
      print_text('      Measures : %-*s key : "%s" '%(30,n,n), '230')
    print_text('      Measures : %-*s key : "%s"'%(30,files[0],files[0]), '230')
     
    # extents of domain :
    nx    =  3010
    ny    =  5460
    dx    =  500
    west  = -645000.0
    east  =  west  + nx*dx
    south = -3370000.0 
    north =  south + ny*dx

    #projection info :
    proj   = 'stere'
    lat_0  = '90'
    lat_ts = '70'
    lon_0  = '-45'
    
    # create projection :
    txt  =   " +proj="   + proj \
           + " +lat_0="  + lat_0 \
           + " +lat_ts=" + lat_ts \
           + " +lon_0="  + lon_0 \
           + " +k=1 +x_0=0 +y_0=0 +no_defs +a=6378137 +rf=298.257223563" \
           + " +towgs84=0.000,0.000,0.000 +to_meter=1"
    p    = Proj(txt)
    
    # save the data in matlab format :
    vara['pyproj_Proj']       = p
    vara['map_western_edge']  = west
    vara['map_eastern_edge']  = east
    vara['map_southern_edge'] = south
    vara['map_northern_edge'] = north
    vara['nx']                = nx
    vara['ny']                = ny
    
    # retrieve data :
    vara['dataset']   = 'measures'
    vara['continent'] = 'greenland'
    for f,n in zip(ftns, files):
      vara[n] = f
    return vara
 
  
  @staticmethod
  def get_rignot():
    
    s    = "::: getting Greenland Rignot data from DataFactory :::"
    print_text(s, DataFactory.color)
    
    global home
    
    direc = home + '/greenland/rignot/velocity_greenland_v4Aug2014.nc'
    data  = netcdf_file(direc, mode = 'r')
    vara  = dict()
    
    needed_vars = {'vx'  : 'vx',
                   'vy'  : 'vy',
                   'err' : 'v_err'}
    
    s    = "    - data-fields collected : python dict key to access -"
    print_text(s, DataFactory.color)
    for v in data.variables:
      try:
        txt = '"' + needed_vars[v] + '"'
      except KeyError:
        txt = ''
      print_text('      Rignot : %-*s key : %s '%(30,v, txt), '230')
    
    # retrieve data :
    vx   = array(data.variables['vx'][:])
    vy   = array(data.variables['vy'][:])
    err  = array(data.variables['err'][:])
    mask = (vx != 0.0).astype('i')
     
    # extents of domain :
    ny,nx =  shape(vx)
    dx    =  150
    west  = -638000.0
    east  =  west + nx*dx
    north = -657600.0
    south =  north - ny*dx

    #projection info :
    proj   = 'stere'
    lat_0  = '90'
    lat_ts = '70'
    lon_0  = '-45'
    
    # create projection :
    txt  =   " +proj="   + proj \
           + " +lat_0="  + lat_0 \
           + " +lat_ts=" + lat_ts \
           + " +lon_0="  + lon_0 \
           + " +k=1 +x_0=0 +y_0=0 +no_defs +a=6378137 +rf=298.257223563" \
           + " +towgs84=0.000,0.000,0.000 +to_meter=1"
    p    = Proj(txt)
    
    # save the data in matlab format :
    vara['pyproj_Proj']       = p
    vara['map_western_edge']  = west 
    vara['map_eastern_edge']  = east 
    vara['map_southern_edge'] = south 
    vara['map_northern_edge'] = north
    vara['nx']                = nx
    vara['ny']                = ny
    
    names = ['vx', 'vy', 'v_err', 'mask']
    ftns  = [ vx,   vy,   err,     mask ]
    
    print_text('      Rignot : %-*s key : "%s"'%(30,names[-1],names[-1]), '230')
    
    # save the data in matlab format :
    vara['dataset']   = 'Rignot'
    vara['continent'] = 'greenland'
    for n, f in zip(names, ftns):
      vara[n] = f[::-1, :]
    return vara
    
  
  @staticmethod
  def get_gre_qgeo_fox_maule():
    
    global home
 
    direc = home + "/greenland/fox_maule/Greenland_heat_flux_5km.nc"
    data  = netcdf_file(direc, mode = 'r')
    vara  = dict()
    
    # retrieve data :
    x     = array(data.variables['x1'][:])
    y     = array(data.variables['y1'][:])
    q_geo = array(data.variables['bheatflx'][:][0]) * 60 * 60 * 24 * 365
 
    # extents of domain :
    east  = max(x)
    west  = min(x)
    north = max(y)
    south = min(y)

    #projection info :
    proj   = 'stere'
    lat_0  = '90'
    lat_ts = '71'
    lon_0  = '-39'
    
    # create projection :
    txt  =   " +proj="   + proj \
           + " +lat_0="  + lat_0 \
           + " +lat_ts=" + lat_ts \
           + " +lon_0="  + lon_0 \
           + " +k=1 +x_0=0 +y_0=0 +no_defs +a=6378137 +rf=298.257223563" \
           + " +towgs84=0.000,0.000,0.000 +to_meter=1"
    p    = Proj(txt)
    
    # save the data in matlab format :
    vara['pyproj_Proj']       = p
    vara['map_western_edge']  = west 
    vara['map_eastern_edge']  = east 
    vara['map_southern_edge'] = south 
    vara['map_northern_edge'] = north
    vara['nx']                = len(x)
    vara['ny']                = len(y)
 
    vara['dataset']   = 'Fox Maule'
    vara['continent'] = 'greenland'
    vara['q_geo']     =  q_geo
    return vara


  @staticmethod
  def get_bedmap1(thklim = 0.0):
    
    s    = "::: getting Bedmap 1 data from DataFactory :::"
    print_text(s, DataFactory.color)
    
    global home
 
    direc = home + '/antarctica/bedmap1/ALBMAPv1.nc'
    data  = netcdf_file(direc, mode = 'r')
    vara  = dict()
    
    needed_vars = {'lsrf'       : 'B',
                   'usrf'       : 'S',
                   'temp'       : 'T',
                   'acca'       : 'acca',
                   'accr'       : 'accr',
                   'ghffm'      : 'ghffm',
                   'ghfsr'      : 'ghfsr'}
    
    s    = "    - data-fields collected : python dict key to access -"
    print_text(s, DataFactory.color)
    for v in data.variables:
      try:
        txt = '"' + needed_vars[v] + '"'
      except KeyError:
        txt = ''
      print_text('      Bedmap 1 : %-*s key : %s '%(30,v, txt), '230')
    
    
    # retrieve data :
    x       = array(data.variables['x1'][:])
    y       = array(data.variables['y1'][:])
    b       = array(data.variables['lsrf'][:])
    h       = array(data.variables['usrf'][:])
    adota   = array(data.variables['acca'][:])
    adotr   = array(data.variables['accr'][:])
    mask    = array(data.variables['mask'][:])
    srfTemp = array(data.variables['temp'][:]) + 273.15
    q_geo_f = array(data.variables['ghffm'][:]) * 60 * 60 * 24 * 365 / 1000
    q_geo_s = array(data.variables['ghfsr'][:]) * 60 * 60 * 24 * 365 / 1000

    H             = h - b
    h[H < thklim] = b[H < thklim] + thklim
    H[H < thklim] = thklim
    
    names = ['B','S','H','acca','accr','ghffm','ghfsr','temp']
    ftns  = [b, h, H, adota, adotr, q_geo_f, q_geo_s, srfTemp]
    
    # extents of domain :
    east    = max(x)
    west    = min(x)
    north   = max(y)
    south   = min(y)

    #projection info :
    proj   = 'stere'
    lat_0  = '-90'
    lat_ts = '-71'
    lon_0  = '0'
    
    # create projection :
    txt  =   " +proj="   + proj \
           + " +lat_0="  + lat_0 \
           + " +lat_ts=" + lat_ts \
           + " +lon_0="  + lon_0 \
           + " +k=1 +x_0=0 +y_0=0 +no_defs +a=6378137 +rf=298.257223563" \
           + " +towgs84=0.000,0.000,0.000 +to_meter=1"
    p    = Proj(txt)
    
    # save the data in matlab format :
    vara['dataset']           = 'bedmap 1'
    vara['continent']         = 'antarctica'
    vara['pyproj_Proj']       = p
    vara['map_western_edge']  = west 
    vara['map_eastern_edge']  = east 
    vara['map_southern_edge'] = south 
    vara['map_northern_edge'] = north
    vara['nx']                = len(x)
    vara['ny']                = len(y)
    for n, f in zip(names, ftns):
      vara[n] = f
    return vara 
  
  
  @staticmethod
  def get_bedmap2(thklim = 0.0):
    
    s    = "::: getting Bedmap 2 data from DataFactory :::"
    print_text(s, DataFactory.color)

    global home
    direc    = home + '/antarctica/bedmap2/bedmap2_tiff/' 
   
    B           = TiffFile(direc + 'bedmap2_bed.tif')
    S           = TiffFile(direc + 'bedmap2_surface.tif') 
    H           = TiffFile(direc + 'bedmap2_thickness.tif')
    mask        = TiffFile(direc + 'bedmap2_icemask_grounded_and_shelves.tif') 
    rock_mask   = TiffFile(direc + 'bedmap2_rockmask.tif') 
    b_uncert    = TiffFile(direc + 'bedmap2_grounded_bed_uncertainty.tif') 
    coverage    = TiffFile(direc + 'bedmap2_coverage.tif')
    gl04c_WGS84 = TiffFile(direc + 'gl04c_geiod_to_WGS84.tif')
    
   
    B           = B.asarray()
    S           = S.asarray()
    H           = H.asarray()
    mask        = mask.asarray()
    rock_mask   = rock_mask.asarray()
    b_uncert    = b_uncert.asarray()
    coverage    = coverage.asarray() 
    gl04c_WGS84 = gl04c_WGS84.asarray()
    
    # format the mask for cslvr :
    mask[mask == 1]   = 2
    mask[mask == 0]   = 1
    mask[mask == 127] = 0
    
    # remove the junk data and impose thickness limit :
    B = S - H
    H[H == 32767]  = thklim
    H[H <= thklim] = thklim
    S = B + H
    
    # generate mask for lateral boundaries :
    Hc = mask.copy(True)
    Hc[mask > 0] = 1
    
    # calculate mask gradient, to properly mark lateral boundaries :
    gradH = gradient(Hc)
    L     = gradH[0]**2 + gradH[1]**2
    L[L > 0.0] = 1.0
    L[L < 1.0] = 0.0

    # mark one more level in :
    Hc[L > 0.0] = 0
    
    gradH = gradient(Hc)
    L2    = gradH[0]**2 + gradH[1]**2
    L2[L2 > 0.0] = 1.0
    L2[L2 < 1.0] = 0.0
    
    # combine them :
    L[L2 > 0.0] = 1.0
    
    vara        = dict()
     
    # extents of domain :
    nx    =  6667
    ny    =  6667
    dx    =  1000
    west  = -3333500.0
    east  =  3333500.0
    north =  3333500.0
    south = -3333500.0

    #projection info :
    proj   = 'stere'
    lat_0  = '-90'
    lat_ts = '-71'
    lon_0  = '0'
    
    # create projection :
    txt  =   " +proj="   + proj \
           + " +lat_0="  + lat_0 \
           + " +lat_ts=" + lat_ts \
           + " +lon_0="  + lon_0 \
           + " +k=1 +x_0=0 +y_0=0 +no_defs +a=6378137 +rf=298.257223563" \
           + " +towgs84=0.000,0.000,0.000 +to_meter=1"
    p    = Proj(txt)
    
    # save the data in matlab format :
    vara['pyproj_Proj']       = p
    vara['map_western_edge']  = west 
    vara['map_eastern_edge']  = east 
    vara['map_southern_edge'] = south 
    vara['map_northern_edge'] = north
    vara['nx']                = nx
    vara['ny']                = ny
    
    names = ['B', 'S', 'H', 'mask', 'lat_mask', 'rock_mask', 'b_uncert', 
             'coverage', 'gl04c_WGS84']
    ftns  = [B, S, H, mask, L, rock_mask, b_uncert, coverage, gl04c_WGS84]
    
    for n in names:
      print_text('      Bedmap 2 : %-*s key : "%s" '%(30,n,n), '230')
   
    # retrieve data :
    vara['dataset']   = 'bedmap 2'
    vara['continent'] = 'antarctica'
    for n, f in zip(names, ftns):
      vara[n] = f[::-1, :]
    return vara 

  
  @staticmethod
  def get_bamber(thklim = 0.0):

    s    = "::: getting Bamber data from DataFactory :::"
    print_text(s, DataFactory.color)
    
    global home
   
    direc = home + '/greenland/bamber13/Greenland_bedrock_topography_V2.nc' 
    data  = netcdf_file(direc, mode = 'r')
    vara  = dict()
    
    needed_vars = {'BedrockElevation' : 'B',
                   'SurfaceElevation' : 'S',
                   'IceThickness'     : 'H',
                   'BedrockError'     : 'Herr',
                   'LandMask'         : 'mask_orig'}
    
    s    = "    - data-fields collected : python dict key to access -"
    print_text(s, DataFactory.color)
    for v in data.variables:
      try:
        txt = '"' + needed_vars[v] + '"'
      except KeyError:
        txt = ''
      print_text('      Bamber : %-*s key : %s '%(30,v, txt), '230')
    
    # retrieve data :
    x         = array(data.variables['projection_x_coordinate'][:])
    y         = array(data.variables['projection_y_coordinate'][:])
    Bo        = array(data.variables['BedrockElevation'][:])
    S         = array(data.variables['SurfaceElevation'][:])
    H         = array(data.variables['IceThickness'][:])
    Herr      = array(data.variables['BedrockError'][:])
    mask_orig = array(data.variables['LandMask'][:])

    # format the mask for cslvr :
    mask = mask_orig.copy(True)
    mask[mask == 1] = 0
    mask[mask == 2] = 1
    mask[mask == 3] = 0
    mask[mask == 4] = 0
    
    # generate mask for lateral boundaries :
    Hc = mask.copy(True)
    
    # calculate mask gradient, to properly mark lateral boundaries :
    gradH = gradient(Hc)
    L     = gradH[0]**2 + gradH[1]**2
    L[L > 0.0] = 1.0
    L[L < 1.0] = 0.0

    # mark one more level in :
    Hc[L > 0.0] = 0
    
    gradH = gradient(Hc)
    L2    = gradH[0]**2 + gradH[1]**2
    L2[L2 > 0.0] = 1.0
    L2[L2 < 1.0] = 0.0
    
    # combine them :
    L[L2 > 0.0] = 1.0
   
    # remove the junk data and impose thickness limit :
    B   = Bo.copy(True)
    H[H == -9999.0] = 0.0
    S[H < thklim] = B[H < thklim] + thklim
    H[H < thklim] = thklim
    B             = S - H

    # extents of domain :
    east  = max(x)
    west  = min(x)
    north = max(y)
    south = min(y)

    #projection info :
    proj   = 'stere'
    lat_0  = '90'
    lat_ts = '71'
    lon_0  = '-39'
    
    # create projection :
    txt  =   " +proj="   + proj \
           + " +lat_0="  + lat_0 \
           + " +lat_ts=" + lat_ts \
           + " +lon_0="  + lon_0 \
           + " +k=1 +x_0=0 +y_0=0 +no_defs +a=6378137 +rf=298.257223563" \
           + " +towgs84=0.000,0.000,0.000 +to_meter=1"
    p    = Proj(txt)
    
    # save the data in matlab format :
    vara['pyproj_Proj']       = p
    vara['map_western_edge']  = west 
    vara['map_eastern_edge']  = east 
    vara['map_southern_edge'] = south 
    vara['map_northern_edge'] = north
    vara['nx']                = len(x)
    vara['ny']                = len(y)
     
    names = ['B', 'Bo', 'S', 'H', 'lat_mask', 'Herr', 'mask', 'mask_orig']
    ftns  = [ B,   Bo,   S,   H,   L,          Herr,   mask,   mask_orig]
    
    # save the data in matlab format :
    vara['dataset']   = 'Bamber'
    vara['continent'] = 'greenland'
    for n, f in zip(names, ftns):
      vara[n] = f
    return vara 
  
  
  @staticmethod
  def get_searise(thklim = 0.0):
    
    s    = "::: getting Searise data from DataFactory :::"
    print_text(s, DataFactory.color)
    
    global home
    
    direc = home + "/greenland/searise/Greenland_5km_dev1.2.nc"
    data  = netcdf_file(direc, mode = 'r')
    vara  = dict()
    
    needed_vars = {'topg'       : 'B',
                   'usrf'       : 'S',
                   'surftemp'   : 'T',
                   'lat'        : 'lat',
                   'lon'        : 'lon',
                   'smb'        : 'adot',
                   'bheatflx'   : 'q_geo',
                   'dhdt'       : 'dhdt',
                   'surfvelmag' : 'U_sar'}
    
    s    = "    - data-fields collected : python dict key to access -"
    print_text(s, DataFactory.color)
    for v in data.variables:
      try:
        txt = '"' + needed_vars[v] + '"'
      except KeyError:
        txt = ''
      print_text('      Searise : %-*s key : %s '%(30,v, txt), '230')
    
    
    # retrieve data :
    x     = array(data.variables['x1'][:])
    y     = array(data.variables['y1'][:])
    S     = array(data.variables['usrf'][:][0])
    adot  = array(data.variables['smb'][:][0])
    B     = array(data.variables['topg'][:][0])
    T     = array(data.variables['surftemp'][:][0]) + 273.15
    q_geo = array(data.variables['bheatflx'][:][0]) * 60 * 60 * 24 * 365
    lat   = array(data.variables['lat'][:][0])
    lon   = array(data.variables['lon'][:][0])
    U_sar = array(data.variables['surfvelmag'][:][0])
    dhdt  = array(data.variables['dhdt'][:][0])
 
    direc = home + "/greenland/searise/smooth_target.mat" 
    U_ob  = loadmat(direc)['st']
    
    H             = S - B
    S[H < thklim] = B[H < thklim] + thklim

    Tn            = 41.83 - 6.309e-3*S - 0.7189*lat - 0.0672*lon + 273
    
    # extents of domain :
    east  = max(x)
    west  = min(x)
    north = max(y)
    south = min(y)

    #projection info :
    proj   = 'stere'
    lat_0  = '90'
    lat_ts = '71'
    lon_0  = '-39'
    
    # create projection :
    txt  =   " +proj="   + proj \
           + " +lat_0="  + lat_0 \
           + " +lat_ts=" + lat_ts \
           + " +lon_0="  + lon_0 \
           + " +k=1 +x_0=0 +y_0=0 +no_defs +a=6378137 +rf=298.257223563" \
           + " +towgs84=0.000,0.000,0.000 +to_meter=1"
    p    = Proj(txt)
    
    # save the data in matlab format :
    vara['pyproj_Proj']       = p
    vara['map_western_edge']  = west 
    vara['map_eastern_edge']  = east 
    vara['map_southern_edge'] = south 
    vara['map_northern_edge'] = north
    vara['nx']                = len(x)
    vara['ny']                = len(y)
 
    names = ['S', 'adot', 'B', 'T', 'q_geo','U_sar', \
             'U_ob', 'lat', 'lon', 'Tn','dhdt']
    ftns  = [S, adot, B, T, q_geo,U_sar, U_ob, lat, lon, Tn, dhdt]

    vara['dataset']   = 'Searise'
    vara['continent'] = 'greenland'
    for n, f in zip(names, ftns):
      vara[n] = f
    return vara
 


