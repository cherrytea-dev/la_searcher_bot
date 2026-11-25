-- Камчатский край: отдельная папка вместо «Прочие поиски ДФО».
--
-- Камчатка висела на дивизионе «Прочие поиски ДФО» (folder 188) и в боте считалась
-- неподдерживаемым регионом: папки с её собственными поисками (510) не было ни в карте
-- регионов, ни в БД. Заводим дивизион и папку, регион RU-KAM перевешиваем на них.
--
-- Идентификаторы не хардкодятся: в проде дивизион «Камчатский край» может уже появиться
-- (тогда новый не создаётся) и его id может отличаться от 78 из тестовых сидов.
-- Папка 510 в проде не занята (максимум в дампе от 25.06.2026 — 459), но и её вставка идемпотентна.
INSERT INTO geo_divisions (division_id, division_name)
SELECT COALESCE((SELECT MAX(division_id) FROM geo_divisions), 0) + 1, 'Камчатский край'
WHERE NOT EXISTS (SELECT 1 FROM geo_divisions WHERE division_name = 'Камчатский край');

INSERT INTO geo_folders (folder_id, division_id, folder_type, folder_subtype)
SELECT 510, d.division_id, 'searches', 'searches active'
FROM geo_divisions d
WHERE d.division_name = 'Камчатский край'
ON CONFLICT (folder_id) DO NOTHING;

UPDATE geo_regions
SET division_id = (SELECT division_id FROM geo_divisions WHERE division_name = 'Камчатский край')
WHERE region_id = 'RU-KAM';
