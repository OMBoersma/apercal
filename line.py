__author__ = "Bjoern Adebahr"
__copyright__ = "ASTRON"
__email__ = "adebahr@astron.nl"

import lib
import logging
import os,sys
import ConfigParser
import lsm
import aipy
import numpy as np
import astropy.io.fits as pyfits

####################################################################################################

class line:
    '''
    Line class to do continuum subtraction and prepare data for line imaging.
    '''
    def __init__(self, file=None, **kwargs):
        self.logger = logging.getLogger('LINE')
        config = ConfigParser.ConfigParser() # Initialise the config parser
        if file != None:
            config.readfp(open(file))
            self.logger.info('### Configuration file ' + file + ' successfully read! ###')
        else:
            config.readfp(open(os.path.realpath(__file__).rstrip('calibrate.pyc') + 'default.cfg'))
            self.logger.info('### No configuration file given or file not found! Using default values! ###')
        for s in config.sections():
            for o in config.items(s):
                setattr(self, o[0], eval(o[1]))
        self.default = config # Save the loaded config file as defaults for later usage

        # Create the directory names
        self.rawdir = self.basedir + self.rawsubdir
        self.crosscaldir = self.basedir + self.crosscalsubdir
        self.selfcaldir = self.basedir + self.selfcalsubdir
        self.linedir = self.basedir + self.linesubdir
        self.finaldir = self.basedir + self.finalsubdir

        # Name the datasets
        self.fluxcal = self.fluxcal.rstrip('MS') + 'mir'
        self.polcal = self.polcal.rstrip('MS') + 'mir'
        self.target = self.target.rstrip('MS') + 'mir'

    #################################################################
    ##### Function to execute the continuum subtraction process #####
    #################################################################

    def go(self):
        '''
        Executes the whole continuum subtraction process in the following order:
        splitdata
        transfergains
        subtract
        '''
        self.logger.info("########## Starting CONTINUUM SUBTRACTION ##########")
        self.splitdata()
        self.transfergains()
        self.subtract()
        self.logger.info("########## CONTINUUM SUBTRACTION done ##########")

    def splitdata(self):
        '''
        Applies calibrator corrections to data, splits the data into chunks in frequency and bins it to the given frequency resolution for the self-calibration
        '''
        if self.splitdata:
            self.director('ch', self.selfcaldir)
            self.logger.info('### Splitting of target data into individual frequency chunks started ###')
            if os.path.isfile(self.linedir + '/' + self.target):
                self.logger.info('# Calibrator corrections already seem to have been applied #')
            else:
                self.logger.info('# Applying calibrator solutions to target data before averaging #')
                uvaver = lib.miriad('uvaver')
                uvaver.vis = self.crosscaldir + '/' + self.target
                uvaver.out = self.linedir + '/' + self.target
                uvaver.go()
                self.logger.info('# Calibrator solutions to target data applied #')
            try:
                uv = aipy.miriad.UV(self.linedir + '/' + self.target)
            except RuntimeError:
                self.logger.error('### No data in your crosscal directory! Exiting pipeline! ###')
                sys.exit(1)
            try:
                nsubband = len(uv['nschan']) # Number of subbands in data
            except TypeError:
                nsubband = 1 # Only one subband in data since exception was triggered
            self.logger.info('# Found ' + str(nsubband) + ' subband(s) in target data #')
            counter = 0 # Counter for naming the chunks and directories
            for subband in range(nsubband):
                self.logger.info('# Started splitting of subband ' + str(subband) + ' #')
                if nsubband == 1:
                    numchan = uv['nschan']
                    finc = np.fabs(uv['sdf'])
                else:
                    numchan = uv['nschan'][subband] # Number of channels per subband
                    finc = np.fabs(uv['sdf'][subband])  # Frequency increment for each channel
                subband_bw = numchan * finc # Bandwidth of one subband
                subband_chunks = round(subband_bw / self.line_splitdata_chunkbandwidth)
                subband_chunks = int(np.power(2, np.ceil(np.log(subband_chunks) / np.log(2)))) # Round to the closest power of 2 for frequency chunks with the same bandwidth over the frequency range of a subband
                if subband_chunks == 0:
                    subband_chunks = 1
                chunkbandwidth = (numchan/subband_chunks)*finc
                self.logger.info('# Adjusting chunk size to ' + str(chunkbandwidth) + ' GHz for regular gridding of the data chunks over frequency #')
                for chunk in range(subband_chunks):
                    self.logger.info('# Starting splitting of data chunk ' + str(chunk) + ' for subband ' + str(subband) + ' #')
                    binchan = round(self.line_splitdata_channelbandwidth / finc)  # Number of channels per frequency bin
                    chan_per_chunk = numchan / subband_chunks
                    if chan_per_chunk % binchan == 0: # Check if the freqeuncy bin exactly fits
                        self.logger.info('# Using frequency binning of ' + str(self.line_splitdata_channelbandwidth) + ' for all subbands #')
                    else:
                        while chan_per_chunk % binchan != 0: # Increase the frequency bin to keep a regular grid for the chunks
                            binchan = binchan + 1
                        else:
                            if chan_per_chunk >= binchan: # Check if the calculated bin is not larger than the subband channel number
                                pass
                            else:
                                binchan = chan_per_chunk # Set the frequency bin to the number of channels in the chunk of the subband
                        self.logger.info('# Increasing frequency bin of data chunk ' + str(chunk) + ' to keep bandwidth of chunks equal over the whole bandwidth #')
                        self.logger.info('# New frequency bin is ' + str(binchan * finc) + ' GHz #')
                    nchan = int(chan_per_chunk/binchan) # Total number of output channels per chunk
                    start = 1 + chunk * chan_per_chunk
                    width = int(binchan)
                    step = int(width)
                    self.director('mk', self.linedir + '/' + str(counter).zfill(2))
                    uvaver = lib.miriad('uvaver')
                    uvaver.vis = self.linedir + '/' + self.target
                    uvaver.out = self.linedir + '/' + str(counter).zfill(2) + '/' + str(counter).zfill(2) + '.mir'
                    uvaver.select = "'" + 'window(' + str(subband+1) + ')' + "'"
                    uvaver.line = "'" + 'channel,' + str(nchan) + ',' + str(start) + ',' + str(width) + ',' + str(step) + "'"
                    uvaver.go()
                    counter = counter + 1
                    self.logger.info('# Splitting of data chunk ' + str(chunk) + ' for subband ' + str(subband) + ' done #')
                self.logger.info('# Splitting of data for subband ' + str(subband) + ' done #')
            self.logger.info('### Splitting of target data into individual frequency chunks done ###')

    # def splitdata(self):
    #     '''
    #     Applies calibrator corrections to data, splits the data into chunks in frequency and bins it to the given frequency resolution for continuum subtraction.
    #     '''
    #     if self.line_splitdata:
    #         self.director('ch', self.linedir)
    #         self.logger.info('### Splitting of target data into individual freqeuncy chunks for continuum subtraction started ###')
    #         uv = aipy.miriad.UV(self.selfcaldir + '/' + self.target)
    #         try:
    #             nsubband = len(uv['nschan'])  # Number of subbands in data
    #         except TypeError:
    #             nsubband = 1  # Only one subband in data since exception was triggered
    #         self.logger.info('# Found ' + str(nsubband) + ' subband(s) in target data #')
    #         counter = 0  # Counter for naming the chunks and directories
    #         for subband in range(nsubband):
    #             self.logger.info('# Started splitting of subband ' + str(subband) + ' #')
    #             if nsubband == 1:
    #                 numchan = uv['nschan']
    #                 finc = np.fabs(uv['sdf'])
    #             else:
    #                 numchan = uv['nschan'][subband]  # Number of channels per subband
    #                 finc = np.fabs(uv['sdf'][subband])  # Frequency increment for each channel
    #             subband_bw = numchan * finc  # Bandwidth of one subband
    #             subband_chunks = round(subband_bw / self.line_splitdata_chunkbandwidth)
    #             subband_chunks = int(np.power(2, np.ceil(np.log(subband_chunks) / np.log(2))))  # Round to the closest power of 2 for frequency chunks with the same bandwidth over the frequency range of a subband
    #             if subband_chunks == 0:
    #                 subband_chunks = 1
    #             chunkbandwidth = (numchan / subband_chunks) * finc
    #             self.logger.info('# Adjusting chunk size to ' + str(chunkbandwidth) + ' GHz for regular gridding of the data chunks over frequency #')
    #             for chunk in range(subband_chunks):
    #                 self.logger.info('# Starting splitting of data chunk ' + str(chunk) + ' for subband ' + str(subband) + ' #')
    #                 binchan = round(self.line_splitdata_channelbandwidth / finc)  # Number of channels per frequency bin
    #                 chan_per_chunk = numchan / subband_chunks
    #                 if chan_per_chunk % binchan == 0:  # Check if the freqeuncy bin exactly fits
    #                     self.logger.info('# Using frequency binning of ' + str(self.line_splitdata_channelbandwidth) + ' for all subbands #')
    #                 else:
    #                     while chan_per_chunk % binchan != 0:  # Increase the frequency bin to keep a regular grid for the chunks
    #                         binchan = binchan + 1
    #                     else:
    #                         if chan_per_chunk >= binchan:  # Check if the calculated bin is not larger than the subband channel number
    #                             pass
    #                         else:
    #                             binchan = chan_per_chunk  # Set the frequency bin to the number of channels in the chunk of the subband
    #                     self.logger.info('# Increasing frequency bin of data chunk ' + str(chunk) + ' to keep bandwidth of chunks equal over the whole bandwidth #')
    #                     self.logger.info('# New frequency bin is ' + str(binchan * finc) + ' GHz #')
    #                 nchan = int(chan_per_chunk / binchan)  # Total number of output channels per chunk
    #                 start = 1 + chunk * chan_per_chunk
    #                 width = int(binchan)
    #                 step = int(width)
    #                 self.director('mk', self.linedir + '/' + str(counter).zfill(2))
    #                 uvaver = lib.miriad('uvaver')
    #                 uvaver.vis = self.selfcaldir + '/' + self.target
    #                 uvaver.out = self.linedir + '/' + str(counter).zfill(2) + '/' + str(counter).zfill(2) + '.mir'
    #                 uvaver.select = "'" + 'window(' + str(subband + 1) + ')' + "'"
    #                 uvaver.line = "'" + 'channel,' + str(nchan) + ',' + str(start) + ',' + str(width) + ',' + str(step) + "'"
    #                 uvaver.go()
    #                 counter = counter + 1
    #                 self.logger.info('# Splitting of data chunk ' + str(chunk) + ' for subband ' + str(subband) + ' done #')
    #             self.logger.info('# Splitting of data for subband ' + str(subband) + ' done #')
    #         self.logger.info('### Splitting of target data into individual frequency chunks done ###')

    def transfergains(self):
        '''
        Checks if the continuum datasets have self calibration gains and copies their gains over.
        '''
        if self.line_transfergains:
            self.director('ch', self.linedir)
            self.logger.info('### Copying gains from continuum to line data ###')
            for chunk in self.list_chunks():
                if os.path.isfile(self.selfcaldir + '/' + chunk + '/' + chunk + '.mir' + '/gains'):
                    gpcopy = lib.miriad('gpcopy')
                    gpcopy.vis = self.selfcaldir + '/' + chunk + '/' + chunk + '.mir'
                    gpcopy.out = chunk + '/' + chunk + '.mir'
                    gpcopy.go()
                    self.logger.info('# Copying gains from continuum to line data for chunk ' + chunk + ' #')
                else:
                    self.logger.warning('# Dataset ' + chunk + '.mir does not seem to have self calibration gains. Cannot copy gains to line data! #')
            self.logger.info('### Gains from continuum to line data copied ###')

    def subtract(self):
        '''
        Module for subtracting the continuum from the line data. Supports uvlin and uvmodel (creating an image in the same way the final continuum imaging is done).
        '''
        if self.line_subtract:
            self.director('ch', self.linedir)
            if self.line_subtract_mode == 'uvlin':
                self.logger.info('### Starting continuum subtraction of individual chunks using uvlin ###')
                for chunk in self.list_chunks():
                    uvlin = lib.miriad('uvlin')
                    uvlin.vis = chunk + '/' + chunk + '.mir'
                    uvlin.out = chunk + '/' + chunk + '_line.mir'
                    uvlin.go()
                    self.logger.info('# Continuum subtraction using uvlin method for chunk ' + chunk + ' done #')
                self.logger.info('### Continuum subtraction using uvlin done! ###')
            elif self.line_subtract_mode == 'uvmodel':
                self.logger.info('### Starting continuum subtraction of individual chunks using uvmodel ###')
                for chunk in self.list_chunks():
                    self.director('ch', self.linedir + '/' + chunk)
                    uvcat = lib.miriad('uvcat')
                    uvcat.vis = chunk + '.mir'
                    uvcat.out = chunk + '_uvcat.mir'
                    uvcat.go()
                    self.logger.info('# Applied gains to chunk ' + chunk + ' for subtraction of continuum model #')
                    if os.path.isdir(self.finaldir + '/continuum/stack/' + chunk + '/model_' + str(self.line_subtract_mode_uvmodel_minorcycle-1).zfill(2)):
                        self.logger.info('# Found model for subtraction in final continuum directory. No need to redo continuum imaging #')
                        self.director('cp', self.linedir + '/' + chunk, file=self.finaldir + '/continuum/stack/' + chunk + '/model_' + str(self.line_subtract_mode_uvmodel_minorcycle-1).zfill(2))
                    else:
                        self.create_uvmodel(chunk)
                    try:
                        uvmodel = lib.miriad('uvmodel')
                        uvmodel.vis = chunk + '_uvcat.mir'
                        uvmodel.model = 'model_' + str(self.line_subtract_mode_uvmodel_minorcycle-1).zfill(2)
                        uvmodel.options = 'subtract,mfs'
                        uvmodel.out = chunk + '_line.mir'
                        uvmodel.go()
                        self.director('rm', chunk + '_uvcat.mir')
                        self.logger.info('### Continuum subtraction using uvmodel method for chunk ' + chunk + ' successful! ###')
                    except:
                        self.logger.warning('### Continuum subtraction using uvmodel method for chunk ' + chunk + ' NOT successful! No continuum subtraction done! ###')
                self.logger.info('### Continuum subtraction using uvmodel done! ###')
            else:
                self.logger.error('### Subtract mode not know. Exiting! ###')
                sys.exit(1)

    #############################################################################
    ##### Subfunction for generating a good continuum model for subtraction #####
    #############################################################################

    def create_uvmodel(self, chunk):
        '''
        chunk: Frequency chunk to create the uvmodel for for subtraction
        '''
        majc = int(self.get_last_major_iteration(chunk) + 1)
        self.logger.info('# Last major self-calibration cycle seems to have been ' + str(majc - 1) + ' #')
        if os.path.isfile(self.linedir + '/' + chunk + '/' + chunk + '.mir/gains'):  # Check if a chunk could be calibrated and has data left
            theoretical_noise = self.calc_theoretical_noise(self.linedir + '/' + chunk + '/' + chunk + '.mir')
            self.logger.info('# Theoretical noise for chunk ' + chunk + ' is ' + str(theoretical_noise / 1000) + ' Jy/beam #')
            theoretical_noise_threshold = self.calc_theoretical_noise_threshold(theoretical_noise)
            self.logger.info('# Your theoretical noise threshold will be ' + str(self.line_subtract_mode_uvmodel_nsigma) + ' times the theoretical noise corresponding to ' + str(theoretical_noise_threshold) + ' Jy/beam #')
            dr_list = self.calc_dr_maj(self.line_subtract_mode_uvmodel_drinit, self.line_subtract_mode_uvmodel_dr0, majc, self.line_subtract_mode_uvmodel_majorcycle_function)
            dr_minlist = self.calc_dr_min(dr_list, majc - 1, self.line_subtract_mode_uvmodel_minorcycle, self.line_subtract_mode_uvmodel_minorcycle_function)
            self.logger.info('# Dynamic range limits for the final minor iterations to clean are ' + str(dr_minlist) + ' #')
            try:
                for minc in range(self.line_subtract_mode_uvmodel_minorcycle):  # Iterate over the minor imaging cycles and masking
                    self.run_continuum_minoriteration(chunk, majc, minc, dr_minlist[minc], theoretical_noise_threshold)
                self.logger.info('### Continuum imaging for subtraction for chunk ' + chunk + ' successful! ###')
            except:
                self.logger.warning('### Continuum imaging for subtraction for chunk ' + chunk + ' NOT successful! Continuum subtraction will provide bad or no results! ###')

    def run_continuum_minoriteration(self, chunk, majc, minc, drmin, theoretical_noise_threshold):
        '''
        Does a continuum minor iteration for imaging
        chunk: The frequency chunk to image and calibrate
        maj: Current major iteration
        min: Current minor iteration
        drmin: maximum dynamic range for minor iteration
        theoretical_noise_threshold: calculated theoretical noise threshold
        '''
        if minc == 0:
            invert = lib.miriad('invert')  # Create the dirty image
            invert.vis = self.linedir + '/' + chunk + '/' + chunk + '.mir'
            invert.map = 'map_' + str(minc).zfill(2)
            invert.beam = 'beam_' + str(minc).zfill(2)
            invert.imsize = self.line_subtract_mode_uvmodel_imsize
            invert.cell = self.line_subtract_mode_uvmodel_cellsize
            invert.stokes = 'i'
            invert.slop = 1
            invert.options = 'mfs,double'
            invert.go()
            imax = self.calc_imax('map_' + str(minc).zfill(2))
            noise_threshold = self.calc_noise_threshold(imax, minc, majc)
            dynamic_range_threshold = self.calc_dynamic_range_threshold(imax, drmin)
            mask_threshold, mask_threshold_type = self.calc_mask_threshold(theoretical_noise_threshold, noise_threshold, dynamic_range_threshold)
            self.director('cp', 'mask_' + str(minc).zfill(2), file=self.selfcaldir + '/' + chunk + '/' + str(majc - 2).zfill(2) + '/mask_' + str(self.line_subtract_mode_uvmodel_minorcycle - 1).zfill(2))
            self.logger.info('# Last mask from self-calibration copied #')
            clean_cutoff = self.calc_clean_cutoff(mask_threshold)
            self.logger.info('# Clean threshold for minor cycle ' + str(minc) + ' was set to ' + str(clean_cutoff) + ' Jy/beam #')
            clean = lib.miriad('clean')  # Clean the image down to the calculated threshold
            clean.map = 'map_' + str(0).zfill(2)
            clean.beam = 'beam_' + str(0).zfill(2)
            clean.out = 'model_' + str(minc).zfill(2)
            clean.cutoff = clean_cutoff
            clean.niters = 100000
            clean.region = '"' + 'mask(mask_' + str(minc).zfill(2) + ')' + '"'
            clean.go()
            self.logger.info('# Minor cycle ' + str(minc) + ' cleaning done #')
            restor = lib.miriad('restor')
            restor.model = 'model_' + str(minc).zfill(2)
            restor.beam = 'beam_' + str(0).zfill(2)
            restor.map = 'map_' + str(0).zfill(2)
            restor.out = 'image_' + str(minc).zfill(2)
            restor.mode = 'clean'
            restor.go()  # Create the cleaned image
            self.logger.info('# Cleaned image for minor cycle ' + str(minc) + ' created #')
            restor.mode = 'residual'
            restor.out = 'residual_' + str(minc).zfill(2)
            restor.go()  # Create the residual image
            self.logger.info('# Residual image for minor cycle ' + str(minc) + ' created #')
            self.logger.info('# Peak of the residual image is ' + str(self.calc_imax('residual_' + str(minc).zfill(2))) + ' Jy/beam #')
            self.logger.info('# RMS of the residual image is ' + str(self.calc_irms('residual_' + str(minc).zfill(2))) + ' Jy/beam #')
        else:
            imax = self.calc_imax('map_' + str(0).zfill(2))
            noise_threshold = self.calc_noise_threshold(imax, minc, majc)
            dynamic_range_threshold = self.calc_dynamic_range_threshold(imax, drmin)
            mask_threshold, mask_threshold_type = self.calc_mask_threshold(theoretical_noise_threshold, noise_threshold, dynamic_range_threshold)
            self.logger.info('# Mask threshold for final imaging minor cycle ' + str(minc) + ' set to ' + str(mask_threshold) + ' Jy/beam #')
            self.logger.info('# Mask threshold set by ' + str(mask_threshold_type) + ' #')
            maths = lib.miriad('maths')
            maths.out = 'mask_' + str(minc).zfill(2)
            maths.exp = '"<' + 'image_' + str(minc - 1).zfill(2) + '>"'
            maths.mask = '"<' + 'image_' + str(minc - 1).zfill(2) + '>.gt.' + str(mask_threshold) + '"'
            maths.go()
            self.logger.info('# Mask with threshold ' + str(mask_threshold) + ' Jy/beam created #')
            clean_cutoff = self.calc_clean_cutoff(mask_threshold)
            self.logger.info('# Clean threshold for minor cycle ' + str(minc) + ' was set to ' + str(clean_cutoff) + ' Jy/beam #')
            clean = lib.miriad('clean')  # Clean the image down to the calculated threshold
            clean.map = 'map_' + str(0).zfill(2)
            clean.beam = 'beam_' + str(0).zfill(2)
            clean.model = 'model_' + str(minc - 1).zfill(2)
            clean.out = 'model_' + str(minc).zfill(2)
            clean.cutoff = clean_cutoff
            clean.niters = 100000
            clean.region = '"' + 'mask(' + 'mask_' + str(minc).zfill(2) + ')' + '"'
            clean.go()
            self.logger.info('# Minor cycle ' + str(minc) + ' cleaning done #')
            restor = lib.miriad('restor')
            restor.model = 'model_' + str(minc).zfill(2)
            restor.beam = 'beam_' + str(0).zfill(2)
            restor.map = 'map_' + str(0).zfill(2)
            restor.out = 'image_' + str(minc).zfill(2)
            restor.mode = 'clean'
            restor.go()  # Create the cleaned image
            self.logger.info('# Cleaned image for minor cycle ' + str(minc) + ' created #')
            restor.mode = 'residual'
            restor.out = 'residual_' + str(minc).zfill(2)
            restor.go()
            self.logger.info('# Residual image for minor cycle ' + str(minc) + ' created #')
            self.logger.info('# Peak of the residual image is ' + str(self.calc_imax('residual_' + str(minc).zfill(2))) + ' Jy/beam #')
            self.logger.info('# RMS of the residual image is ' + str(self.calc_irms('residual_' + str(minc).zfill(2))) + ' Jy/beam #')

    ######################################################################
    ##### Subfunctions for managing the location and naming of files #####
    ######################################################################

    def calc_irms(self, image):
        '''
        Function to calculate the maximum of an image
        image (string): The name of the image file. Must be in MIRIAD-format
        returns (float): the maximum in the image
        '''
        fits = lib.miriad('fits')
        fits.op = 'xyout'
        fits.in_ = image
        fits.out = image + '.fits'
        fits.go()
        image_data = pyfits.open(image + '.fits')  # Open the image
        data = image_data[0].data
        imax = np.nanstd(data)  # Get the standard deviation
        image_data.close()  # Close the image
        self.director('rm', image + '.fits')
        return imax

    def calc_imax(self, image):
        '''
        Function to calculate the maximum of an image
        image (string): The name of the image file. Must be in MIRIAD-format
        returns (float): the maximum in the image
        '''
        fits = lib.miriad('fits')
        fits.op = 'xyout'
        fits.in_ = image
        fits.out = image + '.fits'
        fits.go()
        image_data = pyfits.open(image + '.fits')  # Open the image
        data = image_data[0].data
        imax = np.nanmax(data)  # Get the maximum
        image_data.close()  # Close the image
        self.director('rm', image + '.fits')
        return imax

    def calc_isum(self, image):
        '''
        Function to calculate the sum of the values of the pixels in an image
        image (string): The name of the image file. Must be in MIRIAD-format
        returns (float): the sum of the pxiels in the image
                '''
        fits = lib.miriad('fits')
        fits.op = 'xyout'
        fits.in_ = image
        fits.out = image + '.fits'
        fits.go()
        image_data = pyfits.open(image + '.fits')  # Open the image
        data = image_data[0].data
        isum = np.nansum(data)  # Get the maximum
        image_data.close()  # Close the image
        self.director('rm', image + '.fits')
        return isum

    def calc_dr_maj(self, drinit, dr0, majorcycles, function):
        '''
        Function to calculate the dynamic range limits during major cycles
        drinit (float): The initial dynamic range
        dr0 (float): Coefficient for increasing the dynamic range threshold at each major cycle
        majorcycles (int): The number of major cycles to execute
        function (string): The function to follow for increasing the dynamic ranges. Currently 'power' is supported.
        returns (list of floats): A list of floats for the dynamic range limits within the major cycles.
        '''
        if function == 'square':
            dr_maj = [drinit * np.power(dr0, m) for m in range(majorcycles)]
        else:
            self.logger.error('### Function for major cycles not supported! Exiting! ###')
            sys.exit(1)
        return dr_maj

    def calc_dr_min(self, dr_maj, majc, minorcycles, function):
        '''
        Function to calculate the dynamic range limits during minor cycles
        dr_maj (list of floats): List with dynamic range limits for major cycles. Usually from calc_dr_maj
        majc (int): The major cycles you want to calculate the minor cycle dynamic ranges for
        minorcycles (int): The number of minor cycles to use
        function (string): The function to follow for increasing the dynamic ranges. Currently 'square', 'power', and 'linear' is supported.
        returns (list of floats): A list of floats for the dynamic range limits within the minor cycles.
        '''
        if majc == 0:  # Take care about the first major cycle
            prevdr = 0
        else:
            prevdr = dr_maj[majc - 1]
        # The different options to increase the minor cycle threshold
        if function == 'square':
            dr_min = [prevdr + ((dr_maj[majc] - prevdr) * (n ** 2.0)) / ((minorcycles - 1) ** 2.0) for n in range(minorcycles)]
        elif function == 'power':
            dr_min = [prevdr + np.power((dr_maj[majc] - prevdr), (1.0 / (n))) for n in range(minorcycles)][::-1]  # Not exactly need to work on this, but close
        elif function == 'linear':
            dr_min = [(prevdr + ((dr_maj[majc] - prevdr) / (minorcycles - 1)) * n) for n in range(minorcycles)]
        else:
            self.logger.error('### Function for minor cycles not supported! Exiting! ###')
            sys.exit(1)
        return dr_min

    def calc_mask_threshold(self, theoretical_noise_threshold, noise_threshold, dynamic_range_threshold):
        '''
        Function to calculate the actual mask_threshold and the type of mask threshold from the theoretical noise threshold, noise threshold, and the dynamic range threshold
        theoretical_noise_threshold (float): The theoretical noise threshold calculated by calc_theoretical_noise_threshold
        noise_threshold (float): The noise threshold calculated by calc_noise_threshold
        dynamic_range_threshold (float): The dynamic range threshold calculated by calc_dynamic_range_threshold
        returns (float, string): The maximum of the three thresholds, the type of the maximum threshold
        '''
        # if np.isinf(dynamic_range_threshold) or np.isnan(dynamic_range_threshold):
        #     dynamic_range_threshold = noise_threshold
        mask_threshold = np.max([theoretical_noise_threshold, noise_threshold, dynamic_range_threshold])
        mask_argmax = np.argmax([theoretical_noise_threshold, noise_threshold, dynamic_range_threshold])
        if mask_argmax == 0:
            mask_threshold_type = 'Theoretical noise threshold'
        elif mask_argmax == 1:
            mask_threshold_type = 'Noise threshold'
        elif mask_argmax == 2:
            mask_threshold_type = 'Dynamic range threshold'
        return mask_threshold, mask_threshold_type

    def calc_noise_threshold(self, imax, minor_cycle, major_cycle):
        '''
        Calculates the noise threshold
        imax (float): the maximum in the input image
        minor_cycle (int): the current minor cycle the self-calibration is in
        major_cycle (int): the current major cycle the self-calibration is in
        returns (float): the noise threshold
        '''
        noise_threshold = imax / ((self.line_subtract_mode_uvmodel_c0 + (minor_cycle) * self.line_subtract_mode_uvmodel_c0) * (major_cycle + 1))
        return noise_threshold

    def calc_clean_cutoff(self, mask_threshold):
        '''
        Calculates the cutoff for the cleaning
        mask_threshold (float): the mask threshold to calculate the clean cutoff from
        returns (float): the clean cutoff
        '''
        clean_cutoff = mask_threshold / self.line_subtract_mode_uvmodel_c1
        return clean_cutoff

    def calc_dynamic_range_threshold(self, imax, dynamic_range):
        '''
        Calculates the dynamic range threshold
        imax (float): the maximum in the input image
        dynamic_range (float): the dynamic range you want to calculate the threshold for
        returns (float): the dynamic range threshold
        '''
        if dynamic_range == 0:
            dynamic_range = 8.0
        dynamic_range_threshold = imax / dynamic_range
        return dynamic_range_threshold

    def calc_theoretical_noise_threshold(self, theoretical_noise):
        '''
        Calculates the theoretical noise threshold from the theoretical noise
        theoretical_noise (float): the theoretical noise of the observation
        returns (float): the theoretical noise threshold
        '''
        theoretical_noise_threshold = (self.line_subtract_mode_uvmodel_nsigma * theoretical_noise)
        return theoretical_noise_threshold

    def calc_theoretical_noise(self, dataset):
        '''
        Calculate the theoretical rms of a given dataset
        dataset (string): The input dataset to calculate the theoretical rms from
        returns (float): The theoretical rms of the input dataset as a float
        '''
        uv = aipy.miriad.UV(dataset)
        obsrms = lib.miriad('obsrms')
        try:
            tsys = np.median(uv['systemp'])
            if np.isnan(tsys):
                obsrms.tsys = 30.0
            else:
                obsrms.tsys = tsys
        except KeyError:
            obsrms.tsys = 30.0
        obsrms.jyperk = uv['jyperk']
        obsrms.antdiam = 25
        obsrms.freq = uv['sfreq']
        obsrms.theta = 15
        obsrms.nants = uv['nants']
        obsrms.bw = np.abs(uv['sdf'] * uv['nschan']) * 1000.0
        obsrms.inttime = 12.0 * 60.0
        obsrms.coreta = 0.88
        theorms = float(obsrms.go()[-1].split()[3]) / 1000.0
        return theorms

    def list_chunks(self):
        '''
        Checks how many chunk directories exist and returns a list of them
        '''
        for n in range(100):
            if os.path.exists(self.selfcaldir + '/' + str(n).zfill(2)):
                pass
            else:
                break  # Stop the counting loop at the directory you cannot find anymore
        chunks = range(n)
        chunkstr = [str(i).zfill(2) for i in chunks]
        return chunkstr

    def get_last_major_iteration(self, chunk):
        '''
        Get the number of the last major iteration
        chunk: The frequency chunk to look into. Usually an entry generated by list_chunks
        return: The number of the last major clean iteration for a frequency chunk
        '''
        for n in range(100):
            if os.path.exists(self.selfcaldir + '/' + str(chunk) + '/' + str(n).zfill(2)):
                pass
            else:
                break  # Stop the counting loop at the file you cannot find anymore
        lastmajor = n
        return lastmajor

    #######################################################################
    ##### Manage the creation and moving of new directories and files #####
    #######################################################################

    def show(self, showall=False):
        '''
        show: Prints the current settings of the pipeline. Only shows keywords, which are in the default config file default.cfg
        showall: Set to true if you want to see all current settings instead of only the ones from the current step
        '''
        config = ConfigParser.ConfigParser()
        config.readfp(open(self.apercaldir + '/default.cfg'))
        for s in config.sections():
            if showall:
                print(s)
                o = config.options(s)
                for o in config.items(s):
                    try:
                        print('\t' + str(o[0]) + ' = ' + str(self.__dict__.__getitem__(o[0])))
                    except KeyError:
                        pass
            else:
                if s == 'LINE':
                    print(s)
                    o = config.options(s)
                    for o in config.items(s):
                        try:
                            print('\t' + str(o[0]) + ' = ' + str(self.__dict__.__getitem__(o[0])))
                        except KeyError:
                            pass
                else:
                    pass

    def reset(self):
        '''
        Function to reset the current step and remove all generated data. Be careful! Deletes all data generated in this step!
        '''
        self.logger.warning('### Deleting all continuum subtracted line data. ###')
        self.director('ch', self.linedir)
        self.director('rm', self.linedir + '/*')

    def director(self, option, dest, file=None, verbose=True):
        '''
        director: Function to move, remove, and copy files and directories
        option: 'mk', 'ch', 'mv', 'rm', 'rn', and 'cp' are supported
        dest: Destination of a file or directory to move to
        file: Which file to move or copy, otherwise None
        '''
        if option == 'mk':
            if os.path.exists(dest):
                pass
            else:
                os.mkdir(dest)
                if verbose == True:
                    self.logger.info('# Creating directory ' + str(dest) + ' #')
        elif option == 'ch':
            if os.getcwd() == dest:
                pass
            else:
                self.lwd = os.getcwd()  # Save the former working directory in a variable
                try:
                    os.chdir(dest)
                except:
                    os.mkdir(dest)
                    if verbose == True:
                        self.logger.info('# Creating directory ' + str(dest) + ' #')
                    os.chdir(dest)
                self.cwd = os.getcwd()  # Save the current working directory in a variable
                if verbose == True:
                    self.logger.info('# Moved to directory ' + str(dest) + ' #')
        elif option == 'mv':  # Move
            if os.path.exists(dest):
                lib.basher("mv " + str(file) + " " + str(dest))
            else:
                os.mkdir(dest)
                lib.basher("mv " + str(file) + " " + str(dest))
        elif option == 'rn':  # Rename
            lib.basher("mv " + str(file) + " " + str(dest))
        elif option == 'cp':  # Copy
            lib.basher("cp -r " + str(file) + " " + str(dest))
        elif option == 'rm':  # Remove
            lib.basher("rm -r " + str(dest))
        else:
            print('### Option not supported! Only mk, ch, mv, rm, rn, and cp are supported! ###')