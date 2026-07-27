"""Verify all key packages import correctly in the scs_marine environment."""
import sys

packages = []

try:
    import numpy; packages.append(f'numpy       {numpy.__version__}')
except Exception as e: packages.append(f'numpy       FAILED: {e}')

try:
    import pandas; packages.append(f'pandas      {pandas.__version__}')
except Exception as e: packages.append(f'pandas      FAILED: {e}')

try:
    import xarray; packages.append(f'xarray      {xarray.__version__}')
except Exception as e: packages.append(f'xarray      FAILED: {e}')

try:
    import netCDF4; packages.append(f'netCDF4     {netCDF4.__version__}')
except Exception as e: packages.append(f'netCDF4     FAILED: {e}')

try:
    import scipy; packages.append(f'scipy       {scipy.__version__}')
except Exception as e: packages.append(f'scipy       FAILED: {e}')

try:
    import matplotlib; packages.append(f'matplotlib  {matplotlib.__version__}')
except Exception as e: packages.append(f'matplotlib  FAILED: {e}')

try:
    import seaborn; packages.append(f'seaborn     {seaborn.__version__}')
except Exception as e: packages.append(f'seaborn     FAILED: {e}')

try:
    import cartopy; packages.append(f'cartopy     {cartopy.__version__}')
except Exception as e: packages.append(f'cartopy     FAILED: {e}')

try:
    import PyQt6; packages.append(f'PyQt6       {PyQt6.QtCore.PYQT_VERSION_STR}')
except Exception as e: packages.append(f'PyQt6       FAILED: {e}')

try:
    import openpyxl; packages.append(f'openpyxl    {openpyxl.__version__}')
except Exception as e: packages.append(f'openpyxl    FAILED: {e}')

try:
    import pyinstaller; packages.append(f'pyinstaller installed')
except Exception as e: packages.append(f'pyinstaller FAILED: {e}')

print(f'Python {sys.version}')
for p in packages:
    print(p)

failed = [p for p in packages if 'FAILED' in p]
if failed:
    print(f'\n{len(failed)} package(s) failed!')
    sys.exit(1)
else:
    print('\nAll imports successful!')
