"""PhilHealth dialysis register parsing and honest location matching (synthetic layout fixtures)."""
import pandas as pd

from agap.registers import barangay_name, match_osm, parse_register

LAYOUT = """List of Accredited Freestanding Dialysis Clinics for CY 2026 Updated as of September 30, 2026
          NAME OF HEALTH FACILITY            TEL_NO          EMAIL                 STREET                        MUNICIPALITY   EXPIRE DATE    SEC
 LAGUNA
    610  ALPHA KIDNEY CENTER, INC.           0917-0000000    alpha@example.com     UNIT 1, SOUTH MALL,           BINAN          12/31/2026     P
                                                                                   BRGY. SAN FRANCISCO
  611 BETA DIALYSIS                                                                BRGY POBLACION 1              STA. CRUZ 12/31/2027   P
 LUCENA CITY
    612  GAMMA RENAL                         042-000-0000    gamma@example          13 QUEZON AVE                 LUCENA CITY    12/31/2028     P
                                                             .com
                                                                                 Page 2 of 46
""".splitlines()


def test_register_rows_join_wrapped_streets_and_keep_their_province():
    rows = parse_register(LAYOUT).set_index("entry")
    assert list(rows.index) == [610, 611, 612]
    assert rows.loc[610, "street"] == "UNIT 1, SOUTH MALL, BRGY. SAN FRANCISCO"
    assert rows.loc[610, "province"] == "LAGUNA" and rows.loc[610, "municipality"] == "BINAN"
    assert rows.loc[611, "municipality"] == "STA. CRUZ" and rows.loc[611, "telephone"] == ""
    assert rows.loc[611, "accreditation_expiry"] == "12/31/2027"
    assert rows.loc[612, "province"] == "LUCENA CITY" and rows.loc[612, "email"] == "gamma@example.com"


def test_barangay_names_are_read_from_common_address_spellings():
    assert barangay_name("UNIT 1, SOUTH MALL, BRGY. SAN FRANCISCO") == "SAN FRANCISCO"
    assert barangay_name("175 NATIONAL HIWAY BGY. PACIANO RIZAL") == "PACIANO RIZAL"
    assert barangay_name("KM 31 NATIONAL HIGHWAY, BARANGAY NUEVA") == "NUEVA"
    assert barangay_name("KM 81 MAHARLIKA HIGHWAY") is None


def test_chain_branches_only_match_an_osm_feature_near_their_own_area():
    clinics = pd.DataFrame(dict(name=["KIDNEYCARE DIALYSIS CENTER", "KIDNEYCARE DIALYSIS CENTER", "UNMAPPED CLINIC"]))
    features = [dict(id="node/1", name="Kidneycare", lat=14.29, lon=121.10)]
    anchors = {0: (14.30, 121.11), 1: (14.07, 121.32), 2: (14.29, 121.10)}
    assert {index: feature["id"] for index, feature in match_osm(clinics, features, anchors).items()} == {0: "node/1"}


def test_generic_facility_words_never_pair_different_clinics():
    from agap.registers import name_similarity
    different = [("PAETE RURAL HEALTH UNIT", "Pangil Rural Health Center"), ("CABUYAO CITY HOSPITAL", "Calamba Doctors Hospital"),
                 ("SANTA CRUZ RURAL HEALTH UNIT", "San Pablo Norte Rural Health Unit"), ("LOS BAÑOS RHU I", "Los Baños Rural Health Unit 2"),
                 ("BIÑAN CITY HOSPITAL", "Binan Doctor's Hospital"), ("GLOBAL CARE MEDICAL CENTER OF BAY, INC.", "Global Care Medical Center of Canlubang")]
    same = [("ALAMINOS RURAL HEALTH UNIT", "Alaminos Rural Health Unit"), ("STO. CRISTO RURAL HEALTH UNIT", "Santo Cristo Health Center"),
            ("ST. JAMES HOSPITAL, INC", "Saint James Hospital"), ("HEMOTEK RENAL CENTER, INC.", "Hemotek Renal Center"),
            ("RENAL HUB AND MANAGEMENT, INC.", "Renal Hub Dialysis Center")]
    assert all(name_similarity(a, b) < .65 for a, b in different)
    assert all(name_similarity(a, b) >= .65 for a, b in same)


def test_facility_kind_and_full_name_coverage_reject_place_name_only_matches():
    from agap.registers import same_facility
    assert not same_facility("CALAMBA CITY HEALTH OFFICE", "Calamba Medical Center")
    assert not same_facility("SINILOAN RHU", "Siniloan Diagnostic and Medical Clinic")
    assert not same_facility("SANTA CRUZ RURAL HEALTH UNIT", "Santa Cruz Polymedic Hospital")
    assert not same_facility("COMMUNITY GENERAL HOSPITAL OF SAN PABLO CITY, INC,", "San Pablo City General Hospital")
    assert not same_facility("SAN PABLO CITY GENERAL HOSPITAL", "BLESCES Diagnostic Laboratory - San Pablo")
    assert same_facility("RURAL HEALTH UNIT OF BAY", "Bay Municipal Health Office")
    assert same_facility("PAGSANJAN MEDICAL CLINIC, INC", "Pagsanjan Medical Clinic and General Hospital")
    assert same_facility("KIDNEYCARE DIALYSIS CENTER", "Kidneycare")


def test_registered_service_points_keep_register_ids_and_label_unverified_capability(tmp_path):
    import copy
    import pytest
    from agap.config import load_config
    from agap.data.geography import YAKAP_LOCATIONS, registered_service_points
    path = tmp_path / YAKAP_LOCATIONS
    path.parent.mkdir(parents=True)
    pd.DataFrame(dict(register_id="YAKAP-20260930", entry=[1757, 1758], name=["ALAMINOS RURAL HEALTH UNIT", "OTHER CLINIC"],
                      municipality_name=["Alaminos", "Outside"], latitude=[14.06, 14.2], longitude=[121.25, 121.1],
                      location_precision=["osm", "municipality"])).to_csv(path, index=False)
    cfg = copy.deepcopy(load_config())
    points = registered_service_points(cfg, tmp_path, {"Alaminos"})
    assert points.facility_id.tolist() == ["YAKAP-20260930-1757"]
    assert points.capacity.iloc[0] == cfg["allocation"]["slots_per_registered_site"]
    assert "capability unverified" in points.verification_status.iloc[0]
    with pytest.raises(FileNotFoundError, match="prepare_clinic_locations"):
        registered_service_points(cfg, tmp_path / "missing", {"Alaminos"})
