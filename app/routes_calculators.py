from flask import Blueprint, render_template, request
from flask_login import login_required
from app.utils import get_unit_preference, gallons_to_liters, liters_to_gallons

GALLON_TO_LITER = 3.78541

calculator_bp = Blueprint("calculator_bp", __name__, url_prefix="/calculator")


def _valid_sg(value):
    """Sanity check for a specific-gravity input (e.g. catches 1060 typed instead of 1.060)."""
    return 0.900 <= value <= 1.300


def _valid_pct(value):
    return 0 <= value <= 30


def _valid_co2(value):
    return 0 <= value <= 6


def _valid_temp_c(value):
    return -20 <= value <= 110


@calculator_bp.route("/")
@login_required
def calculator_index():
    return render_template("calculators/index.html")

@calculator_bp.route("/abv", methods=["GET", "POST"])
@login_required
def calculator_abv():
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            og = float(request.form["og"])
            fg = float(request.form["fg"])
            if not (_valid_sg(og) and _valid_sg(fg)):
                raise ValueError("gravity out of range")
            result = round((og - fg) * 131.25, 2)
        except:
            result = None
    return render_template("calculators/abv.html", result=result, unit_preference=units)

@calculator_bp.route("/abv-target", methods=["GET", "POST"])
@login_required
def calculator_abv_target():
    """Estimate how much honey to add to reach a target ABV."""
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            batch_input = float(request.form["volume"])
            batch_gal = batch_input if units == "imperial" else liters_to_gallons(batch_input)
            current_sg = float(request.form["current_gravity"])
            target_abv = float(request.form["target_abv"])
            target_fg = float(request.form.get("target_fg") or 1.000)

            if not (_valid_sg(current_sg) and _valid_sg(target_fg) and _valid_pct(target_abv)):
                result = {"error": "Values look out of range - gravity like 1.050, ABV as a plain percent like 12."}
            else:
                target_og = (target_abv / 131.25) + target_fg
                added_points = target_og - current_sg

                if added_points <= 0:
                    result = {"error": "Target ABV is not higher than current potential."}
                else:
                    # Honey adds ~35 points per pound per gallon
                    pounds_needed = round((added_points * batch_gal * 1000) / 35, 2)
                    if units == "metric":
                        result = {
                            "amount": round(pounds_needed * 0.453592, 2),
                            "unit": "kg",
                            "target_og": round(target_og, 3)
                        }
                    else:
                        result = {
                            "amount": pounds_needed,
                            "unit": "lb",
                            "target_og": round(target_og, 3)
                        }
        except Exception:
            result = {"error": "Invalid input"}
    return render_template("calculators/abv_target.html", result=result, unit_preference=units)

@calculator_bp.route("/dilution", methods=["GET", "POST"])
@login_required
def calculator_dilution():
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            original_volume_input = float(request.form["original_volume"])
            original_volume = original_volume_input if units == "imperial" else liters_to_gallons(original_volume_input)
            original_gravity = float(request.form["original_gravity"])
            target_gravity = float(request.form["target_gravity"])

            if not (_valid_sg(original_gravity) and _valid_sg(target_gravity)):
                result = "Gravity values look out of range - enter as e.g. 1.060, not 1060."
            elif target_gravity >= original_gravity:
                result = "Target gravity must be lower than original gravity."
            else:
                new_volume = (original_volume * (original_gravity - 1)) / (target_gravity - 1)
                added_water_gal = new_volume - original_volume
                added_water = round(gallons_to_liters(added_water_gal) if units == "metric" else added_water_gal, 2)
                unit_label = "liters" if units == "metric" else "gallons"
                result = f"Add {added_water} {unit_label} of water."
        except:
            result = "Invalid input"
    return render_template("calculators/dilution.html", result=result, unit_preference=units)

@calculator_bp.route("/volume-recovery", methods=["GET", "POST"])
@login_required
def calculator_volume_recovery():
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            current_volume_input = float(request.form["current_volume"])
            target_volume_input = float(request.form["target_volume"])
            current_volume = current_volume_input if units == "imperial" else liters_to_gallons(current_volume_input)
            target_volume = target_volume_input if units == "imperial" else liters_to_gallons(target_volume_input)
            original_gravity = float(request.form["original_gravity"])

            if not _valid_sg(original_gravity):
                raise ValueError("gravity out of range")

            lost_volume = target_volume - current_volume
            gravity_points = original_gravity - 1.0
            honey_per_gallon = (1000 / 35) * gravity_points  # 35 gravity points per lb honey per gallon (meadmakr.com)
            honey_needed = round(honey_per_gallon * lost_volume, 2)
            water_needed_gal = lost_volume - (honey_needed / 12)
            if units == "metric":
                result = {
                    "honey": round(honey_needed * 0.453592, 2),
                    "water": round(gallons_to_liters(water_needed_gal), 2),
                    "unit": "liters",
                    "honey_unit": "kg"
                }
            else:
                result = {
                    "honey": honey_needed,
                    "water": round(water_needed_gal, 2),
                    "unit": "gallons",
                    "honey_unit": "lb"
                }
        except:
            result = None
    return render_template("calculators/volume_recovery.html", result=result, unit_preference=units)

@calculator_bp.route("/honey-needed", methods=["GET", "POST"])
@login_required
def calculator_honey_needed():
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            batch_size_input = float(request.form["volume"])
            batch_size = batch_size_input if units == "imperial" else liters_to_gallons(batch_size_input)
            target_og = float(request.form["target_gravity"])
            if not _valid_sg(target_og):
                raise ValueError("gravity out of range")
            gravity_points = target_og - 1.0
            honey_lb = round(batch_size * gravity_points * (1000 / 35), 2)  # 35 points/lb/gal
            if units == "metric":
                result = {"amount": round(honey_lb * 0.453592, 2), "unit": "kg"}
            else:
                result = {"amount": honey_lb, "unit": "lb"}
        except:
            result = "Invalid input"
    return render_template("calculators/honey_required.html", result=result, unit_preference=units)

@calculator_bp.route("/sweetness", methods=["GET", "POST"])
@login_required
def calculator_sweetness():
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            vol_input = float(request.form["batch_volume"])
            gallons = vol_input if units == "imperial" else liters_to_gallons(vol_input)
            target_sg = float(request.form["target_gravity"])
            current_sg = float(request.form["current_gravity"])

            if not (_valid_sg(target_sg) and _valid_sg(current_sg)):
                raise ValueError("gravity out of range")

            delta = target_sg - current_sg
            honey_lb = round(gallons * delta * (1000 / 35), 2)  # 35 points/lb/gal
            if units == "metric":
                result = {"amount": round(honey_lb * 0.453592, 2), "unit": "kg"}
            else:
                result = {"amount": honey_lb, "unit": "lb"}
        except:
            result = None
    return render_template("calculators/sweetness.html", result=result, unit_preference=units)

@calculator_bp.route("/carbonation", methods=["GET", "POST"])
@login_required
def calculator_carbonation():
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            volume_input = float(request.form["volume"])
            volume = volume_input if units == "imperial" else liters_to_gallons(volume_input)
            co2 = float(request.form["target_co2"])
            if not _valid_co2(co2):
                raise ValueError("co2 out of range")
            sugar_oz = round(volume * (co2 - 0.85) * 0.536, 2)  # 15.195 g priming sugar per gal per CO2 vol (Brew-by-the-Numbers/Kaiser formula)
            if units == "metric":
                result = {"amount": round(sugar_oz * 28.3495, 2), "unit": "grams"}
            else:
                result = {"amount": sugar_oz, "unit": "oz"}
        except:
            result = "Invalid input"
    return render_template("calculators/carbonation.html", result=result, unit_preference=units)

@calculator_bp.route("/tosna", methods=["GET", "POST"])
@login_required
def calculator_tosna():
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            batch_size_input = float(request.form["batch_size"])
            batch_size = batch_size_input if units == "imperial" else liters_to_gallons(batch_size_input)
            starting_gravity = float(request.form["starting_gravity"])

            if not _valid_sg(starting_gravity):
                result = "Gravity looks out of range - enter as e.g. 1.090, not 1090."
            elif starting_gravity < 1.050:
                result = "OG too low for TOSNA."
            else:
                must_liters = batch_size * GALLON_TO_LITER
                # ~1 g/L Fermaid-O for a standard 14% ABV mead, scaled to batch potential ABV (demijohnjournal.com TOSNA calculator)
                potential_abv = (starting_gravity - 1.0) * 131.25
                total = round((potential_abv / 14.0) * must_liters, 2)
                per_day = round(total / 4, 2)
                result = type("TOSNAResult", (object,), {"total": total, "per_day": per_day})()
        except Exception as e:
            result = "Invalid input"
            print("TOSNA error:", e)

    return render_template("calculators/tosna.html", result=result, unit_preference=units)

@calculator_bp.route("/temp-correction", methods=["GET", "POST"])
@login_required
def calculator_temp_correction():
    result = None
    units = get_unit_preference()
    if request.method == "POST":
        try:
            # template fields are named reading/sample_temp/calibration_temp and are always in Celsius
            observed = float(request.form["reading"])
            sample_temp_c = float(request.form["sample_temp"])
            calibration_temp_c = float(request.form["calibration_temp"])
            if not (_valid_sg(observed) and _valid_temp_c(sample_temp_c) and _valid_temp_c(calibration_temp_c)):
                raise ValueError("value out of range")
            sample_temp_f = (sample_temp_c * 9/5) + 32
            calibration_temp_f = (calibration_temp_c * 9/5) + 32
            def _sg_poly(t):  # ASBC/Petit hydrometer correction polynomial (maltcalcs.com, homebrewacademy.com), t in Fahrenheit
                return 1.00130346 - 0.000134722124 * t + 0.00000204052596 * t**2 - 0.00000000232820948 * t**3
            corrected = round(observed * (_sg_poly(sample_temp_f) / _sg_poly(calibration_temp_f)), 3)
            result = corrected
        except:
            result = None
    return render_template("calculators/temp_correction.html", result=result, unit_preference=units)
