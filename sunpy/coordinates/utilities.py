# -*- coding: utf-8 -*-
from __future__ import absolute_import, division
import datetime
import warnings

import numpy as np
import astropy.units as u
from astropy.time import Time
from astropy.coordinates import SkyCoord, Angle, Longitude, PrecessedGeocentric, AltAz, \
                                get_body_barycentric
from astropy.coordinates.representation import CartesianRepresentation, SphericalRepresentation
from astropy._erfa.core import ErfaWarning

from sunpy.time import parse_time

from .frames import HeliographicStonyhurst as HGS
from .transformations import _sun_detilt_matrix

__all__ = ['get_earth', 'get_sun_B0', 'get_sun_L0', 'get_sun_P', 'get_sunearth_distance',
           'get_sun_orientation']


def _astropy_time(time):
    """
    Return an `~astropy.time.Time` instance, running it through `~sunpy.time.parse_time` if needed
    """
    return time if isinstance(time, Time) else Time(parse_time(time))


def get_earth(time='now'):
    """
    Return a SkyCoord for the location of the Earth at a specified time in the
    HeliographicStonyhurst frame.  The longitude will be 0 by definition.

    Parameters
    ----------
    time : various
        Time to use as `~astropy.time.Time` or in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.SkyCoord`
        SkyCoord for the location of the Earth in the HeliographicStonyhurst frame
    """
    obstime = _astropy_time(time)

    earth_icrs = get_body_barycentric('earth', obstime)
    earth = SkyCoord(earth_icrs, frame='icrs', obstime=obstime).transform_to(HGS)

    # Explicitly set the longitude to 0
    earth = SkyCoord(0*u.deg, earth.lat, earth.radius, frame=earth)

    return earth


def get_sun_B0(time='now'):
    """
    Return the B0 angle for the Sun at a specified time, which is the heliographic latitude of the
    Sun-disk center as seen from Earth.  The range of B0 is +/-7.23 degrees.

    Parameters
    ----------
    time : various
        Time to use as `~astropy.time.Time` or in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Angle`
        The position angle
    """
    return Angle(get_earth(time).lat)


# Ignore warnings that result from going back in time to the first Carrington rotation
with warnings.catch_warnings():
    warnings.simplefilter("ignore", ErfaWarning)

    # Carrington rotation 1 starts late in the day on 1853 Nov 9
    # according to Astronomical Algorithms (Meeus 1998, p.191)
    _time_first_rotation = Time('1853-11-09 21:36')

    # Longitude of Earth at Carrington rotation 1 in de-tilted HCRS (so that solar north pole is Z)
    _lon_first_rotation = \
        get_earth(_time_first_rotation).hcrs.cartesian.transform(_sun_detilt_matrix) \
        .represent_as(SphericalRepresentation).lon.to('deg')


def get_sun_L0(time='now'):
    """
    Return the L0 angle for the Sun at a specified time, which is the Carrington longitude of the
    Sun-disk center as seen from Earth.

    Parameters
    ----------
    time : various
        Time to use as `~astropy.time.Time` or in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Longitude`
        The Carrington longitude
    """
    obstime = _astropy_time(time)

    # Calculate the longitude due to the Sun's rotation relative to the stars
    # A sidereal rotation is defined to be exactly 25.38 days
    sidereal_lon = Longitude((obstime.jd - _time_first_rotation.jd) / 25.38 * 360*u.deg)

    # Calculate the longitude of the Earth in de-tilted HCRS
    lon_obstime = get_earth(obstime).hcrs.cartesian.transform(_sun_detilt_matrix) \
                  .represent_as(SphericalRepresentation).lon.to('deg')

    return Longitude(lon_obstime - _lon_first_rotation - sidereal_lon)


def get_sun_P(time='now'):
    """
    Return the position (P) angle for the Sun at a specified time, which is the angle between
    geocentric north and solar north as seen from Earth, measured eastward from geocentric north.
    The range of P is +/-26.3 degrees.

    Parameters
    ----------
    time : various
        Time to use as `~astropy.time.Time` or in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Angle`
        The position angle
    """
    obstime = _astropy_time(time)

    geocentric = PrecessedGeocentric(equinox=obstime, obstime=obstime)

    return _sun_north_angle_to_z(geocentric)


def get_sunearth_distance(time='now'):
    """
    Return the distance between the Sun and the Earth at a specified time.

    Parameters
    ----------
    time : various
        Time to use as `~astropy.time.Time` or in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Distance`
        The Sun-Earth distance
    """
    return get_earth(time).radius


def get_sun_orientation(location, time='now'):
    """
    Return the orientation angle for the Sun from a specified Earth location and time.  The
    orientation angle is the angle between local zenith and solar north, measured eastward from
    local zenith.

    Parameters
    ----------
    location : `~astropy.coordinates.EarthLocation`
        Observer location on Earth
    time : various
        Time to use as `~astropy.time.Time` or in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Angle`
        The orientation of the Sun
    """
    obstime = _astropy_time(time)

    local_frame = AltAz(obstime=obstime, location=location)

    return _sun_north_angle_to_z(local_frame)


def _sun_north_angle_to_z(frame):
    """
    Return the angle between solar north and the Z axis of the provided frame's coordinate system
    and observation time.
    """
    # Find the Sun center and Sun north in HGS at the frame's observation time
    sun_center = SkyCoord(0*u.deg, 0*u.deg, 0*u.km, frame=HGS, obstime=frame.obstime)
    sun_north = SkyCoord(0*u.deg, 90*u.deg, 690000*u.km, frame=HGS, obstime=frame.obstime)

    # Find the Sun center and Sun north in the frame's coordinate system
    sky_normal = sun_center.transform_to(frame).data.to_cartesian()
    sun_north = sun_north.transform_to(frame).data.to_cartesian()

    # Use cross products to obtain the sky projections of the two vectors (rotated by 90 deg)
    sun_north_in_sky = sun_north.cross(sky_normal)
    z_in_sky = CartesianRepresentation(0, 0, 1).cross(sky_normal)

    # Normalize directional vectors
    sky_normal /= sky_normal.norm()
    sun_north_in_sky /= sun_north_in_sky.norm()
    z_in_sky /= z_in_sky.norm()

    # Calculate the signed angle between the two projected vectors
    cos_theta = sun_north_in_sky.dot(z_in_sky)
    sin_theta = sun_north_in_sky.cross(z_in_sky).dot(sky_normal)
    angle = np.arctan2(sin_theta, cos_theta).to('deg')

    return Angle(angle)
