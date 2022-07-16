#!/usr/bin/env python

import os
import sys
import subprocess
import traceback
import time
import shutil
import urllib.request

# python -m pip install --user opencv-python
import cv2

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


def main(args=sys.argv):
  images = dl_imagery()

  deep_field_nircam_tif = cv2.imread( images.path('first-deep-field', 'nircam') )
  deep_field_miri_tif = cv2.imread( images.path('first-deep-field', 'miri') )
  
  print(f'deep_field_nircam_tif={deep_field_nircam_tif}')
  print(f'deep_field_miri_tif={deep_field_miri_tif}')
  

  






if __name__ == '__main__':
  main()

