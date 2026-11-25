-- Камчатский край: отдельная папка вместо «Прочие поиски ДФО».
--
-- Камчатка висела на дивизионе «Прочие поиски ДФО» (папка 188) и в боте считалась
-- неподдерживаемым регионом: папки с её собственными поисками (510) не было ни в карте
-- регионов, ни в БД. Заводим дивизион и папку, регион RU-KAM перевешиваем на них.
--
-- Идентификаторы не хардкодятся: в проде дивизион «Камчатский край» может уже появиться
-- (тогда новый не создаётся) и его id может отличаться от 78 из тестовых сидов.
-- Номер папки 510 захардкожен, потому что он же стоит в карте регионов бота. Если в проде
-- этот id уже занят другой папкой (в том числе архивной/справочной, у которых division_id
-- пустой), миграция падает, а не подписывает камчатцев на чужой регион: тогда нужен
-- свободный id здесь и в src/communicate/_utils/regions.py.
INSERT INTO geo_divisions (division_id, division_name)
SELECT COALESCE((SELECT MAX(division_id) FROM geo_divisions), 0) + 1, 'Камчатский край'
WHERE NOT EXISTS (SELECT 1 FROM geo_divisions WHERE division_name = 'Камчатский край');

-- LEFT JOIN: у архивных и справочных папок division_id пустой, и именно такая папка
-- скорее всего и окажется на месте 510, если номер уже занят.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM geo_folders f
        LEFT JOIN geo_divisions d ON d.division_id = f.division_id
        WHERE f.folder_id = 510
          AND (
              d.division_name IS DISTINCT FROM 'Камчатский край'
              OR f.folder_type IS DISTINCT FROM 'searches'
              OR f.folder_subtype IS DISTINCT FROM 'searches active'
          )
    ) THEN
        RAISE EXCEPTION
            'geo_folders.folder_id = 510 already belongs to another folder; '
            'pick a free folder_id for Камчатский край in this migration and in regions.py';
    END IF;
END $$;

INSERT INTO geo_folders (folder_id, division_id, folder_type, folder_subtype)
SELECT 510, d.division_id, 'searches', 'searches active'
FROM geo_divisions d
WHERE d.division_name = 'Камчатский край'
ORDER BY d.division_id
LIMIT 1
ON CONFLICT (folder_id) DO NOTHING;

-- Если папка 510 уже была, регион идёт за ней: имя дивизиона не уникально, и «минимальный
-- id» мог бы оказаться не тем дивизионом, к которому привязана папка.
UPDATE geo_regions
SET division_id = COALESCE(
    (SELECT f.division_id FROM geo_folders f WHERE f.folder_id = 510),
    (
        SELECT division_id FROM geo_divisions
        WHERE division_name = 'Камчатский край'
        ORDER BY division_id
        LIMIT 1
    )
)
WHERE region_id = 'RU-KAM';
