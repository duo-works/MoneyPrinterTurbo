"""Alt yazi metninde tire kalmamali (kanal sahibi, 2026-08-12).

Istek: "metinlerde alt yazi metinler '-' isareti bulunmasin, son uretilenlerde
vardi". Sikayet dogruydu ve olculdu — son 6 senaryoda:

    alone—and          (uzun tire, cumle kesmesi)
    paper—not          (uzun tire, cumle kesmesi)
    post-conspiracy    (kelime ici tire)
    single-handedly    (kelime ici tire)
    pre-telescopic     (kelime ici tire)
    Anglo-Dutch        (kelime ici tire, ozel ad)

Alt yazi SRT'si seslendirme metninden uretiliyor; tireyi SRT'den silmek
zamanlama bloklarini bozardi. Bu yuzden temizlik plan kurulurken, kaynakta
yapiliyor.
"""

import youtube_automation as ya


def test_uzun_tire_virgule_donuyor():
    """Olculen gercek cumle — Hayek senaryosunun ilk satiri."""
    cikti = ya.tiresiz_anlatim("Hayek did not win alone—and not simply for defending markets.")

    assert cikti == "Hayek did not win alone, and not simply for defending markets."


def test_bosluklu_uzun_tire_cift_noktalama_birakmiyor():
    cikti = ya.tiresiz_anlatim("The record stops here — no one knows why.")

    assert cikti == "The record stops here, no one knows why."
    assert " ," not in cikti


def test_kelime_ici_tire_bosluga_donuyor():
    cikti = ya.tiresiz_anlatim("She acted single-handedly in the post-conspiracy years.")

    assert cikti == "She acted single handedly in the post conspiracy years."


def test_sayi_araligi_bosluga_degil_to_ya_donuyor():
    """⚠️ Bosluk verseydi alt yazida iki AYRI yil gibi okunurdu ve
    seslendirme de oyle soylerdi. Aralik anlami korunmali."""
    assert ya.tiresiz_anlatim("The war lasted 1652-1674.") == "The war lasted 1652 to 1674."
    assert ya.tiresiz_anlatim("The war lasted 1652–1674.") == "The war lasted 1652 to 1674."


def test_hicbir_tire_turu_geride_kalmiyor():
    metin = ya.tiresiz_anlatim("a—b, c–d, e-f, g―h, i‒j")

    for tire in "-—–―‒":
        assert tire not in metin


def test_zaten_temiz_metin_degismiyor():
    metin = "No one has found her grave. The record stops at the citation."

    assert ya.tiresiz_anlatim(metin) == metin


def test_baslikta_ozel_addaki_tire_KALIYOR():
    """⚠️ Baslik alt yazi degil, ARAMA metni. "Anglo-Dutch War" yazimini
    bozmak YouTube aramasinda tam eslesmeyi kaybettirir; istegin karsiligi
    olmayan bir gorunurluk bedeli olurdu. Uzun tire yine de dusuyor."""
    assert ya.tiresiz_baslik("The Anglo-Dutch War") == "The Anglo-Dutch War"
    assert ya.tiresiz_baslik("Who Was She — And Why?") == "Who Was She, And Why?"


def test_plan_kurulurken_anlatim_temizleniyor():
    """Asil kosul: tek tek islevler degil, HATTIN kendisi temiz metin uretmeli."""
    plan = ya.ContentPlan(
        topic="t",
        visual_anchor="a",
        title=ya.tiresiz_baslik("A-B — C"),
        script=ya.tiresiz_anlatim("She worked single-handedly—for years."),
        scenes=[{"narration": ya.tiresiz_anlatim("A pre-telescopic sky."), "search_term": "x y"}],
        description=ya.tiresiz_baslik("D — E"),
        tags=["a", "b", "c"],
    )

    assert "-" not in plan.script
    assert "—" not in plan.script
    assert "-" not in plan.scenes[0]["narration"]
    assert "—" not in plan.title and "—" not in plan.description


def test_yonerge_tire_yasagini_soyluyor_ve_kendisi_ornek_olmuyor():
    """⚠️ Yonergeye kurali yazmak tek basina yetmez, ama yonergenin KENDISI
    uzun tire kullaniyorsa kural ornegiyle celisir. Ikisi de kontrol ediliyor.
    """
    yonerge = ya.editoryal_sistem_yonergesi()

    assert "NEVER USE A DASH CHARACTER" in yonerge
    assert "—" not in yonerge
    assert "–" not in yonerge
