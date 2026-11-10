# Contributing

Bug reports, ideas and pull requests are welcome.

## Reporting a problem

Open an [issue](https://github.com/ildargiv/KopiTehnik-Print/issues) with the program version (Settings, About), the Windows version, the printer model and driver, and the steps that lead to the problem. For colour or borderless problems a photo of the print next to the test sheet helps a lot. Security problems go through [SECURITY.md](SECURITY.md), not through public issues.

## Running from source

Windows 10 or 11, Python 3.12.

```
pip install -r requirements-lock.txt
python photo_crop_qt.py
```

`requirements-lock.txt` holds the exact versions the release is built with; `requirements.txt` is the unpinned list.

## Before a pull request

```
python -m pytest tests -q
python photo_crop_qt.py --selftest
```

The self-test builds the main window, walks through the dialogs and prints a report; every line must start with `OK`. The same checks run on GitHub for every pull request (the `tests` workflow).

- Keep one change per pull request and say what you tested and on which printer, if printing is involved.
- Interface strings are written in Russian in the source and translated in `i18n.py`, `i18n_more.py` and `i18n_161.py`. A new string needs at least the English translation.
- Do not commit local dumps, build output or detection models (`*.onnx`).

## Licence of contributions

The program is distributed under the [KopiTehnik Print Licence](LICENSE), which is not an open-source licence. By submitting a contribution you grant the Licensor the rights described in section 5 of the licence. If you cannot agree to that, please open an issue describing the change instead of sending code.
