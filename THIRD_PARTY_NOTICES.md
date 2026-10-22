# Third-party notices

KopiTehnik Print is licensed under the [KopiTehnik Print Licence 1.0](LICENSE). The components below are not covered by that licence: each keeps its own licence and copyright. Full licence texts are in the packages themselves (the `*.dist-info/licenses` folders of the installed wheels) and at the links given.

## Python libraries (listed in requirements.txt)

| Component | Licence | Notes |
|---|---|---|
| Pillow | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| NumPy | BSD-3-Clause | https://numpy.org |
| OpenCV (opencv-python) | Apache-2.0 | The wheel also bundles FFmpeg (LGPL-2.1) and, in the non-headless build, Qt (LGPL). https://github.com/opencv/opencv-python |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| pi-heif | BSD-3-Clause | HEIC/HEIF decoding only. Its binary wheels bundle libheif and libde265 (both LGPL-3.0). https://github.com/bigcat88/pillow_heif |
| PySide6 (Qt for Python) | LGPL-3.0 | Qt is dynamically linked; source: https://code.qt.io. See "LGPL components" below. |
| PyInstaller (build tool only) | GPL-2.0 with bootloader exception | The exception allows distributing the produced executables under any licence. |

HEIC support deliberately uses `pi-heif`, not `pillow-heif`: the Windows wheels of `pillow-heif` include the x265 encoder (GPL-2.0), which this program does not need (it only reads HEIC).

## Models downloaded on demand

| Model | Licence | Used for |
|---|---|---|
| YuNet (OpenCV Zoo) | MIT | face detection in smart crop |
| YOLOX (Megvii) | Apache-2.0 | people and pets detection |
| MediaPipe BlazePose (OpenCV Zoo) | Apache-2.0 | body pose in the enhanced crop method |
| Real-ESRGAN realesr-general-x4v3 (Xintao Wang et al.) | BSD-3-Clause | AI photo upscaling (converted to ONNX, weights unchanged) |

Models are downloaded by the user's request into `%APPDATA%\PhotoCrop\models` and are not part of the installer.

## Not shipped

The optional YOLO-pose detector in `smart_crop.py` can load a model file that the user supplies. Ultralytics YOLO models are licensed under AGPL-3.0, so this program neither ships nor downloads them. Using such a model is the user's own responsibility.

## LGPL components (Qt / PySide6, FFmpeg, libheif, libde265)

These libraries are used unmodified. You may replace them with your own compatible build of the same library and use the Software with it, and you may reverse engineer the Software to the extent needed to debug such a replacement. Source code of each library is available at the upstream locations above. Nothing in the KopiTehnik Print Licence restricts these rights.

Free distribution and paid distribution (sale of copies, or distribution as part of a paid service) both require these notices to be shipped with the program. For paid distribution the LGPL additionally requires that the recipient can actually replace the Qt libraries. The official build is currently a single PyInstaller executable, which makes replacement hard. Before copies are sold, either switch to a folder build (onedir, where the Qt DLLs are separate files in the program folder) or obtain a commercial Qt licence. Running from source (`run_qt.bat`) always satisfies this.

This file is informational and is not legal advice.
