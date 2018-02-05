CREATE TABLE `utilities` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `electricity_ht` int(11) DEFAULT NULL,
  `electricity_lt` int(11) DEFAULT NULL,
  `water` float DEFAULT NULL,
  `gas` float DEFAULT NULL,
  `averageTemp` float DEFAULT NULL,
  PRIMARY KEY (`id`)
) DEFAULT CHARSET=utf8 COLLATE=utf8_bin
