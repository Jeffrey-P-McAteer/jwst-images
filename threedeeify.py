#!/usr/bin/env python

import os
import sys
import subprocess
import traceback
import time
import shutil
import urllib.request
import socket
import ssl
import random
import pickle

# python -m pip install --user opencv-python
import cv2

# python -m pip install --user numpy
import numpy

# python -m pip install --user scikit-image
import skimage
import skimage.measure

# python -m pip install --user imutils
import imutils
import imutils.contours

# python -m pip install --user aiohttp
import aiohttp.web


class ImgList(list):
  def path(self, *nicknames):
    for i in self:
      all_nicknames_match = True
      for nickname in nicknames:
        if not nickname in i:
          all_nicknames_match = False
      if all_nicknames_match:
        return i
    return None

def dl_imagery(target_dir='out'):
  os.makedirs(target_dir, exist_ok=True)
  # See https://webbtelescope.org/resource-gallery/images?itemsPerPage=100&Type=Observations&keyword=&=

  images_to_dl = [
    ('https://stsci-opo.org/STScI-01G7DDBNAV8SHNRTMT9AHGC5MF.tif', 'first-deep-field-nircam.tif'),
    ('https://stsci-opo.org/STScI-01G7WE6PKJJ1ZXYKM04SPGMZYD.tif', 'first-deep-field-miri.tif'),
  ]

  all_images = ImgList()
  for img_url, filename in images_to_dl:
    target_file = os.path.join(target_dir, filename)
    all_images.append(os.path.abspath(target_file))
    if os.path.exists(target_file) and os.path.getsize(target_file) > 0:
      print(f'Exists: {target_file}')
      continue
    print(f'Downloading {img_url} to {target_file}')
    urllib.request.urlretrieve(img_url, target_file)

  return all_images


def get_ssl_cert_and_key_or_generate():
  ssl_dir = 'ssl'
  if not os.path.exists(ssl_dir):
    os.makedirs(ssl_dir)
  
  key_file = os.path.join(ssl_dir, 'server.key')
  cert_file = os.path.join(ssl_dir, 'server.crt')

  if os.path.exists(key_file) and os.path.exists(cert_file):
    return cert_file, key_file
  else:
    if os.path.exists(key_file):
      os.remove(key_file)
    if os.path.exists(cert_file):
      os.remove(cert_file)
  
  if not shutil.which('openssl'):
    raise Exception('Cannot find the tool "openssl", please install this so we can generate ssl certificates for our servers! Alternatively, manually create the files {} and {}.'.format(cert_file, key_file))

  generate_cmd = ['openssl', 'req', '-x509', '-sha256', '-nodes', '-days', '28', '-newkey', 'rsa:2048', '-keyout', key_file, '-out', cert_file]
  subprocess.run(generate_cmd, check=True)

  return cert_file, key_file


def get_local_ip():
    """Try to determine the local IP address of the machine."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Use Google Public DNS server to determine own IP
        sock.connect(('8.8.8.8', 80))

        return sock.getsockname()[0]
    except socket.error:
        try:
            return socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            return '127.0.0.1'
    finally:
        sock.close() 

def crop(img_px, x, y, w, h):
  return img_px[y:y+h, x:x+w]

def rgba_make_transparent_where(img_px, alpha_val=128, condition_statement=lambda x, y, pixel: False):
  for y in range(0, len(img_px)):
    for x in range(0, len(img_px[y])):
      if condition_statement(x, y, img_px[y][x]):
        r = 0
        g = 1
        b = 2
        a = 3
        img_px[y][x][a] = alpha_val

  return img_px

def rgba_make_black_transparent(img_px):
  r = 0
  g = 1
  b = 2
  a = 3
  for y in range(0, len(img_px)):
    for x in range(0, len(img_px[y])):
      # Compute brightness
      px_r = img_px[y][x][r]
      px_g = img_px[y][x][g]
      px_b = img_px[y][x][b]

      img_px[y][x][a] = max(0, min(255, int( ((px_r + px_g + px_b) / (3)) * 3.0 ) ))
      
      # Make dark patches agressively more transparent!
      if img_px[y][x][a] < 84:
        img_px[y][x][a] = int( img_px[y][x][a] * 0.75 )
      # if img_px[y][x][a] < 12:
      #   img_px[y][x][a] = 0

      if img_px[y][x][a] > 84:
        img_px[y][x][a] *= 1.5 # 50% brighter

      if img_px[y][x][a] > 250:
        img_px[y][x][a] = 255

  return img_px


def get_xy_wh(image_pixels, transparent_pixel=None, counted_pixel=None):
  if transparent_pixel is None and counted_pixel is None:
    raise Exception('Must set either counted_pixel or transparent_pixel')
  min_x = 999999999
  max_x = 0
  min_y = 999999999
  max_y = 0
  for y in range(0, len(image_pixels)):
    for x in range(0, len(image_pixels[y])):
      if transparent_pixel is not None:
        if not (image_pixels[y][x] == transparent_pixel):
          if x < min_x:
            min_x = x
          if x > max_x:
            max_x = x
          if y < min_y:
            min_y = y
          if y > max_y:
            max_y = y
      
      if counted_pixel is not None:
        if (image_pixels[y][x] == counted_pixel):
          if x < min_x:
            min_x = x
          if x > max_x:
            max_x = x
          if y < min_y:
            min_y = y
          if y > max_y:
            max_y = y


  return min_x, min_y, max_x - min_x, max_y - min_y



def main(args=sys.argv):
  images = dl_imagery()

  image_tag = 'first-deep-field'
  image_nircam_tif = cv2.imread( images.path(image_tag, 'nircam') )
  #image_miri_tif = cv2.imread( images.path(image_tag, 'miri') )

  # Image begins in sRGB color space
  image_nircam_tif = cv2.cvtColor(image_nircam_tif, cv2.COLOR_RGB2RGBA)

  make_quest_2_modifications = True # Set to false for the whole image

  if make_quest_2_modifications:
    # This value shown to be the largest the Oculus 2 can hangle before it's GPU falls over.
    performance_crop_size_px = 1024 * 3
    # Ensure always <= image size
    full_h = len(image_nircam_tif)
    full_w = len(image_nircam_tif[0])
    performance_crop_size_px = min(performance_crop_size_px, min(full_h, full_w) )
    # pick random x/y offsets that fit within image to increase variety
    performance_crop_x = random.randint(0, full_w - performance_crop_size_px)
    performance_crop_y = random.randint(0, full_h - performance_crop_size_px)
    image_nircam_tif = crop(image_nircam_tif, performance_crop_x, performance_crop_y, performance_crop_size_px, performance_crop_size_px) # Make image much smaller to facilitate R&D
    print(f'Warning: using cropped image for fast r&d, {performance_crop_size_px}x{performance_crop_size_px} instead of the full {full_w}x{full_h}')

  entire_img_png_bytes = cv2.imencode('.png', image_nircam_tif)[1].tobytes()

  image_nircam_tif_annotated = image_nircam_tif.copy()
  
  # Segment nircam into a list of features with x,y coordinates in pixels
  image_features = [
    # {'.png': bytes(), 'x': 0, 'y': 0, 'w': 12, 'h': 12, },
  ]
  # Compute image_features
  nircam_grey = cv2.cvtColor(image_nircam_tif, cv2.COLOR_RGBA2GRAY)
  
  blur_px = 3 # must be odd
  nircam_grey_blur = cv2.GaussianBlur(nircam_grey, (blur_px, blur_px), 0)

  thresh_min = 60
  nircam_grey_thresh = cv2.threshold(nircam_grey_blur, thresh_min, 255, cv2.THRESH_BINARY)[1]
  
  # Clean up noise
  nircam_grey_thresh = cv2.erode(nircam_grey_thresh, None, iterations=2)
  nircam_grey_thresh = cv2.dilate(nircam_grey_thresh, None, iterations=4)

  nircam_grey_thresh = cv2.threshold(nircam_grey_thresh, thresh_min, 255, cv2.THRESH_BINARY)[1]


  nircam_labels = skimage.measure.label(nircam_grey_thresh, connectivity=2, background=0, return_num=False)
  print(f'nircam_labels={nircam_labels}')

  nircam_regions = skimage.measure.regionprops(nircam_labels)
  
  nircam_mask_min_size = 4

  for region in nircam_regions:
    if make_quest_2_modifications and len(image_features) > 498:
      print(f'Ignoring region={region} because we already have {len(image_features)} features and make_quest_2_modifications={make_quest_2_modifications}. The quest looks like it breaks badly if we give it >500 images.')
      continue
    
    print(f'bbox={region.bbox}')
  
    y0, x0 = region.centroid
    #min_x, min_y, max_x, max_y = region.bbox
    min_y, min_x, max_y, max_x = region.bbox
    width = max_x - min_x
    height = max_y - min_y

    if width < nircam_mask_min_size or height < nircam_mask_min_size:
      continue

    segment_img_px = crop(image_nircam_tif, min_x, min_y, width, height)

    # And now we will do a smaller-scale threshold to mask & convert dark pixels to transparent
    segment_img_grey = cv2.cvtColor(segment_img_px, cv2.COLOR_RGBA2GRAY)
    #segment_img_thresh_a = cv2.threshold(segment_img_grey, 60, 255, cv2.THRESH_BINARY)[1]

    # For all pixels < 120, scale down. For all >120, scale up.
    for _y in range(0, len(segment_img_grey)):
      for _x in range(0, len(segment_img_grey[_y])):
        if segment_img_grey[_y][_x] < 60:
          segment_img_grey[_y][_x] = max(0,   int( segment_img_grey[_y][_x] * 0.60 ) )
        elif segment_img_grey[_y][_x] < 80:
          segment_img_grey[_y][_x] = max(0,   int( segment_img_grey[_y][_x] * 0.80 ) )
        elif segment_img_grey[_y][_x] < 128:
          segment_img_grey[_y][_x] = max(0,   int( segment_img_grey[_y][_x] * 0.90 ) )
        elif segment_img_grey[_y][_x] < 180:
          segment_img_grey[_y][_x] = min(255, int( segment_img_grey[_y][_x] * 1.10 ) )
        elif segment_img_grey[_y][_x] < 240:
          segment_img_grey[_y][_x] = min(255, int( segment_img_grey[_y][_x] * 1.20 ) )
        else:
          segment_img_grey[_y][_x] = min(255, int( segment_img_grey[_y][_x] * 1.30 ) )

        if segment_img_grey[_y][_x] < 35:
          segment_img_grey[_y][_x] = 0


    
    chan_r, chan_g, chan_b, orig_a = cv2.split(segment_img_px)
    #chan_rgba = [chan_r, chan_g, chan_b, segment_img_thresh_a]
    chan_rgba = [chan_r, chan_g, chan_b, segment_img_grey]
    trans_segment_img_px = cv2.merge(chan_rgba, 4)

    segment_d = {
      #'.png': cv2.imencode('.png', segment_img_px)[1].tobytes(),
      '.png': cv2.imencode('.png', trans_segment_img_px)[1].tobytes(),
      'x': min_x,
      'y': min_y,
      'w': width,
      'h': height,
    }
    #print(f'segment_d={segment_d}')
    image_features.append(segment_d)
    print(f'Saved segment number {len(image_features)}')

    image_nircam_tif_annotated = cv2.rectangle(
      image_nircam_tif_annotated,
      (min_x, min_y), (max_x, max_y), # pt1, pt2
      (240, 0, 0, 255), # rgba pixel
      thickness = 2
    )

  image_nircam_tif_annotated_png_bytes = cv2.imencode('.png', image_nircam_tif_annotated)[1].tobytes()
  nircam_grey_thresh_png_bytes = cv2.imencode('.png', nircam_grey_thresh)[1].tobytes()

  print(f'Computed {len(image_features)} image_features')
  
  # Generate aframe html code

  scene_html_s = ""
  # Define a camera that can move in VR land
#   scene_html_s += '''
# <a-entity id="camera-parent" movement-controls="enabled: true; constrainToNavMesh: false; speed: 0.25; fly: true;" position="0 1 0" camera-property-listener>
#   <a-entity id="camera" camera position="0 0 0" look-controls="pointerLockEnabled: false;"></a-entity>
#   <!-- <a-entity cursor="rayOrigin:mouse" raycaster="objects: .raytarget"></a-entity>
#   <a-entity laser-controls="hand: right"></a-entity> -->
# </a-entity>
# '''
  scene_html_s += '''
<!-- Camera + controllers rig -->
<script>
function a_btn_down() { // go down
  try {
    document.querySelector("a-scene").camera.el.parentNode.object3D.position.y -= 1;
  }
  catch (e) { }
  document.querySelector("a-scene").camera.el.object3D.position.y -= 1;
}
function b_btn_down() { // go up
  try {
    document.querySelector("a-scene").camera.el.parentNode.object3D.position.y += 1;
  }
  catch (e) { }
  document.querySelector("a-scene").camera.el.object3D.position.y += 1;
}

AFRAME.registerComponent('threedeeify-abyx-height-adjustment',{
  init: function () {
    this.el.addEventListener('abuttondown', this.on_abuttondown);
    this.el.addEventListener('bbuttondown', this.on_bbuttondown);
    this.el.addEventListener('xbuttondown', this.on_xbuttondown);
    this.el.addEventListener('ybuttondown', this.on_ybuttondown);
  },
  on_abuttondown: function (evt) {
    a_btn_down();
  },
  on_bbuttondown: function (evt) {
    b_btn_down();
  },
  on_xbuttondown: function (evt) {
    a_btn_down();
  },
  on_ybuttondown: function (evt) {
    b_btn_down();
  }
});

</script>
<a-entity id="rig">
  <a-camera position="0 1 0"></a-camera>
  <a-entity oculus-touch-controls="hand: left" threedeeify-abyx-height-adjustment></a-entity>
  <a-entity oculus-touch-controls="hand: right" oculus-thumbstick-controls threedeeify-abyx-height-adjustment></a-entity>
</a-entity>
'''
#   scene_html_s += '''
# <a-entity position="1.01 0 0" rotation="0 0 0" text="value: 1-0-0; color: #fe0e0e; side: double;"></a-entity>
# <a-entity position="0 1.01 0" rotation="0 0 0" text="value: 0-1-0; color: #0efe0e; side: double;"></a-entity>
# <a-entity position="0 0 1.01" rotation="0 0 0" text="value: 0-0-1; color: #0e0efe; side: double;"></a-entity>
#   '''
  #scene_html_s += '''<a-image transparent="true" position="0 3 -31" src="img/all" width="30" height="30"></a-image>'''

  back_begin = -1
  back_end = -16

  for i, feature in enumerate(image_features):
    depth_val = float( random.randrange(min(back_begin, back_end)*100, max(back_begin, back_end)*100) / 100.0)
    x = feature.get('x', 0)
    y = feature.get('y', 0)
    w = feature.get('w', 0)
    h = feature.get('h', 0)
    
    # Scale down, Normalize a bit to fit in default view pane
    x -= 256 * 2
    y -= 1024 * 2
    
    x /= 120.0
    y /= 120.0
    
    w /= 50.0
    h /= 50.0

    # Bias depth so the larger a feature is (in px/50.0), the closer it will generally be to 0 (aka closer to the user)
    depth_val /= ((w*h)**( 1/6 )) * 0.1


    scene_html_s += f'<a-image transparent="true" position="{x} {y} {depth_val}" src="img/{i}" width="{w}" height="{h}"></a-image>\n'
    print(f'Added feature {i} at {round(x, 2)},{round(y, 2)} depth={round(depth_val, 2)}')

  print(f'Generated <a-image> for  {len(image_features)} image_features')

  index_html_s = """<!DOCTYPE html>
<html>
  <head>
    <title>"""+image_tag+""" Projection Viewer</title>
    <script src="https://aframe.io/releases/1.3.0/aframe.min.js"></script>
    <!-- thanks https://stackoverflow.com/questions/71131300/cant-move-camera-in-a-frame-with-oculus-quest-2 -->
    <script src="https://gftruj.github.io/webzamples/aframe/controls/oculus-thumbstick-controls.js"></script>
  </head>
  <body>
    <a-scene background="color: #000000">
      """+scene_html_s+"""
    </a-scene>
  </body>
</html>
"""


  # Host aframe html code
  http_port = 4430
  cert_file, key_file = get_ssl_cert_and_key_or_generate()
  server = aiohttp.web.Application()

  async def http_index_req_handler(req):
    nonlocal index_html_s
    return aiohttp.web.Response(text=index_html_s, content_type='text/html')

  async def http_debug_req_handler(req):
    nonlocal index_html_s
    return aiohttp.web.Response(text='''
      <img src="img/all" style="max-width:98%" /><br>
      <img src="img/thresh" style="max-width:98%" /><br>
      <img src="img/anno" style="max-width:98%" /><br>
'''.strip(), content_type='text/html')

  async def http_image_req_handler(req):
    nonlocal image_features
    nonlocal entire_img_png_bytes
    star_id = req.match_info.get('star_id', 'none')

    # Debugging
    if 'all' in star_id:
      return aiohttp.web.Response(body=entire_img_png_bytes, content_type='image/png')
    elif 'thresh' in star_id:
      return aiohttp.web.Response(body=nircam_grey_thresh_png_bytes, content_type='image/png')
    elif 'anno' in star_id:
      return aiohttp.web.Response(body=image_nircam_tif_annotated_png_bytes, content_type='image/png')
    
    try:
      star_id_num = int(star_id)
      if star_id_num >= 0 and star_id_num < len(image_features):
        return aiohttp.web.Response(body=image_features[star_id_num]['.png'], content_type='image/png')
    except:
      traceback.print_exc()
    # Default
    return aiohttp.web.Response(body=entire_img_png_bytes, content_type='image/png')

  server.add_routes([
    aiohttp.web.get('/', http_index_req_handler),
    aiohttp.web.get('/index.html', http_index_req_handler),
    aiohttp.web.get('/debug', http_debug_req_handler),
    aiohttp.web.get('/img/{star_id}', http_image_req_handler),
  ])

  ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
  ssl_ctx.load_cert_chain(cert_file, key_file)
  
  print()
  print(f'Listening on https://0.0.0.0:{http_port}/')
  print(f'LAN address is https://{get_local_ip()}:{http_port}/')
  print()
  aiohttp.web.run_app(server, ssl_context=ssl_ctx, port=http_port)






if __name__ == '__main__':
  main()

