-- phpMyAdmin SQL Dump
-- version 5.2.1deb1+deb12u1
-- https://www.phpmyadmin.net/
--
-- Host: localhost:3306
-- Erstellungszeit: 10. Feb 2026 um 07:39
-- Server-Version: 10.11.14-MariaDB-0+deb12u2
-- PHP-Version: 8.2.29

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Datenbank: `ifkg`
--

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `auszuege`
--

CREATE TABLE `auszuege` (
  `id` int(11) NOT NULL,
  `bankid` varchar(64) NOT NULL,
  `acctid` varchar(64) NOT NULL,
  `dtposted` datetime NOT NULL,
  `betrag` decimal(12,2) NOT NULL,
  `name` varchar(255) DEFAULT NULL,
  `memo` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `auszuege`
--

INSERT INTO `auszuege` (`id`, `bankid`, `acctid`, `dtposted`, `betrag`, `name`, `memo`) VALUES
(1, '20111', '84722039000', '2025-05-02 00:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Lehne', '022520047003 WEG 3423 St. Andrae-Woerdern, Lehne'),
(2, '20111', '84722039000', '2025-05-02 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(3, '20111', '84722039000', '2025-05-02 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Mai 2025, Bahngasse 14 Anna Bondar'),
(4, '20111', '84722039000', '2025-05-05 00:00:00', -221.94, 'Tamara Pieringer', 'OBI, Weide-Sichtschutz Tamara Pieringer'),
(5, '20111', '84722039000', '2025-05-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(6, '20111', '84722039000', '2025-05-05 00:00:00', 831.23, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(7, '20111', '84722039000', '2025-05-05 00:00:00', 892.41, 'Katharina Reicher', 'Miete april 2025 Katharina Reicher'),
(8, '20111', '84722039000', '2025-05-06 00:00:00', 40.80, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(9, '20111', '84722039000', '2025-05-06 00:00:00', 1044.75, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(10, '20111', '84722039000', '2025-05-12 00:00:00', -609.46, 'Marktgemeinde St. Andrä-Wördern', '008273003082 Marktgemeinde St. Andrae-Woerdern'),
(11, '20111', '84722039000', '2025-05-15 00:00:00', -885.13, 'FA Tulln', '223849191 FA Tulln'),
(12, '20111', '84722039000', '2025-05-22 00:00:00', -70.82, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62704 EVN AG'),
(13, '20111', '84722039000', '2025-05-30 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(14, '20111', '84722039000', '2025-05-30 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(15, '20111', '84722039000', '2025-05-30 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(16, '20111', '84722039000', '2025-05-30 00:00:00', 892.41, 'Katharina Reicher', 'Miete Mai 2025 Katharina Reicher'),
(17, '20111', '84722039000', '2025-06-02 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(18, '20111', '84722039000', '2025-06-02 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Juni 2025, Bahngasse 1 Anna Bondar'),
(19, '20111', '84722039000', '2025-06-03 00:00:00', 831.23, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(20, '20111', '84722039000', '2025-06-04 00:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Lehne', '022520047003 WEG 3423 St. Andrae-Woerdern, Lehne'),
(21, '20111', '84722039000', '2025-06-04 00:00:00', 40.80, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(22, '20111', '84722039000', '2025-06-04 00:00:00', 1044.75, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(23, '20111', '84722039000', '2025-06-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(24, '20111', '84722039000', '2025-06-24 00:00:00', -53.36, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62011 EVN AG'),
(25, '20111', '84722039000', '2025-06-25 00:00:00', -16.81, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '306-8436636-2046721 Amazon.de 29LOA AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(26, '20111', '84722039000', '2025-06-25 00:00:00', -159.58, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '306-8436636-2046721 Amazon.de 6SPW1 AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(27, '20111', '84722039000', '2025-06-30 00:00:00', -14.19, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(28, '20111', '84722039000', '2025-06-30 00:00:00', -240.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(29, '20111', '84722039000', '2025-06-30 00:00:00', -400.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(30, '20111', '84722039000', '2025-06-30 00:00:00', 0.00, 'unbekannt', '*** Abschlussbuchung per 30.06.2025 **** Reklamationen bitte binnen 2 Monaten'),
(31, '20111', '84722039000', '2025-06-30 00:00:00', 0.92, 'unbekannt', 'Habenzinsen'),
(32, '20111', '84722039000', '2025-06-30 00:00:00', -0.23, 'unbekannt', 'Kest'),
(33, '20111', '84722039000', '2025-06-30 00:00:00', -21.24, 'unbekannt', 'Kostenbeitrag Digital Banking'),
(34, '20111', '84722039000', '2025-06-30 00:00:00', -29.73, 'unbekannt', 'Kontofuehrung'),
(35, '20111', '84722039000', '2025-06-30 00:00:00', -7.35, 'unbekannt', 'Bereitstellung Debitkarte'),
(36, '20111', '84722039000', '2025-06-30 00:00:00', -22.92, 'unbekannt', 'Buchungskostenbeitrag'),
(37, '20111', '84722039000', '2025-04-01 00:00:00', -2894.94, 'Helvetia Versicherungen AG', '2583067018/POL 4002544175 4/2025 HE Helvetia Versicherungen AG'),
(38, '20111', '84722039000', '2025-04-02 00:00:00', -1279.14, 'Baierl GmbH', '250183523 Baierl GmbH'),
(39, '20111', '84722039000', '2025-04-02 00:00:00', 892.41, 'Katharina Reicher', 'Miete maerz 2025 Katharina Reicher'),
(40, '20111', '84722039000', '2025-04-03 00:00:00', 831.23, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(41, '20111', '84722039000', '2025-04-04 00:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Lehne', '022520047003 WEG 3423 St. Andrae-Woerdern, Lehne'),
(42, '20111', '84722039000', '2025-04-04 00:00:00', 40.80, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(43, '20111', '84722039000', '2025-04-04 00:00:00', 1044.75, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(44, '20111', '84722039000', '2025-04-07 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(45, '20111', '84722039000', '2025-04-11 00:00:00', -41.46, 'Frieda Fuchs', 'Gartenutensilien BK Frieda Fuchs'),
(46, '20111', '84722039000', '2025-04-11 00:00:00', -960.00, 'INTER-TREUHAND Prachner', '232745 253777 INTER-TREUHAND Prachner'),
(47, '20111', '84722039000', '2025-04-11 00:00:00', 31276.93, 'Ing. Baierl Gesellschaft m.b.H.', 'Ruckzahlung Ing. Baierl Gesellschaft m.b.H.'),
(48, '20111', '84722039000', '2025-04-17 00:00:00', -89.92, 'FA Tulln', '223849191 FA Tulln'),
(49, '20111', '84722039000', '2025-04-22 00:00:00', -151.32, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62603 EVN AG'),
(50, '20111', '84722039000', '2025-04-30 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(51, '20111', '84722039000', '2025-04-30 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(52, '20111', '84722039000', '2025-04-30 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(53, '20111', '84722039000', '2025-03-03 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(54, '20111', '84722039000', '2025-03-03 00:00:00', 831.23, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(55, '20111', '84722039000', '2025-03-03 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Maerz 2025, Bahngasse 1 Anna Bondar'),
(56, '20111', '84722039000', '2025-03-04 00:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Lehne', '022520047003 WEG 3423 St. Andrae-Woerdern, Lehne'),
(57, '20111', '84722039000', '2025-03-04 00:00:00', 40.80, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(58, '20111', '84722039000', '2025-03-04 00:00:00', 1044.75, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(59, '20111', '84722039000', '2025-03-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(60, '20111', '84722039000', '2025-03-10 00:00:00', -24.00, 'Netz NOe GmbH', '20805074 Netz NOe GmbH'),
(61, '20111', '84722039000', '2025-03-17 00:00:00', 668.80, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Rueckzahlung VS 01+02/25 Top 5/11 WEG 3423 St. Andrae-Woerdern, Lehne'),
(62, '20111', '84722039000', '2025-03-20 00:00:00', -176.95, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62804 EVN AG'),
(63, '20111', '84722039000', '2025-03-27 00:00:00', -419.00, 'AMAZON PAYMENTS EUROPE S.C.A.', 'P02-2723730-0610722 amzn.com/pmts 1 AMAZON PAYMENTS EUROPE S.C.A.'),
(64, '20111', '84722039000', '2025-03-31 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(65, '20111', '84722039000', '2025-03-31 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(66, '20111', '84722039000', '2025-03-31 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(67, '20111', '84722039000', '2025-03-31 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(68, '20111', '84722039000', '2025-03-31 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Apr 2025, Bahngasse 14 Anna Bondar'),
(69, '20111', '84722039000', '2025-03-31 00:00:00', 0.00, 'unbekannt', '*** Abschlussbuchung per 31.03.2025 **** Reklamationen bitte binnen 2 Monaten'),
(70, '20111', '84722039000', '2025-03-31 00:00:00', 0.26, 'unbekannt', 'Habenzinsen'),
(71, '20111', '84722039000', '2025-03-31 00:00:00', -0.07, 'unbekannt', 'Kest'),
(72, '20111', '84722039000', '2025-03-31 00:00:00', -21.24, 'unbekannt', 'Kostenbeitrag Digital Banking'),
(73, '20111', '84722039000', '2025-03-31 00:00:00', -29.73, 'unbekannt', 'Kontofuehrung'),
(74, '20111', '84722039000', '2025-03-31 00:00:00', -7.35, 'unbekannt', 'Bereitstellung Debitkarte'),
(75, '20111', '84722039000', '2025-03-31 00:00:00', -25.71, 'unbekannt', 'Buchungskostenbeitrag'),
(76, '20111', '84722039000', '2025-02-03 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(77, '20111', '84722039000', '2025-02-03 00:00:00', 831.23, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(78, '20111', '84722039000', '2025-02-03 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Fab 2025, Bahngasse 14 Anna Bondar'),
(79, '20111', '84722039000', '2025-02-04 00:00:00', 40.80, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(80, '20111', '84722039000', '2025-02-04 00:00:00', 1044.75, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(81, '20111', '84722039000', '2025-02-05 00:00:00', -334.40, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 02252 0041 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(82, '20111', '84722039000', '2025-02-05 00:00:00', -640.72, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 02252 0047 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(83, '20111', '84722039000', '2025-02-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(84, '20111', '84722039000', '2025-02-05 00:00:00', 892.00, 'Katharina Reicher', 'Miete februar 25 Katharina Reicher'),
(85, '20111', '84722039000', '2025-02-07 00:00:00', -10000.00, 'Thomas Fuchs', 'Privatentnahme Thomas Fuchs'),
(86, '20111', '84722039000', '2025-02-10 00:00:00', -616.48, 'Marktgemeinde St. Andrä-Wördern', '008193002885 Marktgemeinde St. Andrae-Woerdern'),
(87, '20111', '84722039000', '2025-02-27 00:00:00', 892.41, 'Katharina Reicher', 'Miete februar 2025 Katharina Reicher'),
(88, '20111', '84722039000', '2025-02-28 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(89, '20111', '84722039000', '2025-02-28 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(90, '20111', '84722039000', '2025-02-28 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(91, '20111', '84722039000', '2025-02-28 00:00:00', -228.75, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62103 EVN AG'),
(92, '20111', '84722039000', '2025-01-02 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(93, '20111', '84722039000', '2025-01-02 00:00:00', 880.00, 'Katharina Reicher', 'Miete Jaenner 2025 Katharina Reicher'),
(94, '20111', '84722039000', '2025-01-02 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Jan 2025, Bahngasse 14 Anna Bondar'),
(95, '20111', '84722039000', '2025-01-02 00:00:00', 1289.92, 'Martina Fuchs', 'Stg.5/Top11 Miete 9,10,11,12/2024 Martina Fuchs'),
(96, '20111', '84722039000', '2025-01-03 00:00:00', 831.23, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(97, '20111', '84722039000', '2025-01-07 00:00:00', -15000.00, 'Thomas Fuchs', 'Privatentnahme Thomas Fuchs'),
(98, '20111', '84722039000', '2025-01-07 00:00:00', 40.80, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(99, '20111', '84722039000', '2025-01-07 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(100, '20111', '84722039000', '2025-01-07 00:00:00', 1044.75, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(101, '20111', '84722039000', '2025-01-08 00:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 02252 0047 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(102, '20111', '84722039000', '2025-01-08 00:00:00', -334.40, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 02252 0041 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(103, '20111', '84722039000', '2025-01-13 00:00:00', -608.40, 'Intertreuhand Prachner', '232745 252563 Intertreuhand Prachner'),
(104, '20111', '84722039000', '2025-01-17 00:00:00', 0.00, 'unbekannt', 'Guthaben auf Girokonten und Spareinlagen sind gemaess Einlagensicherungs- und'),
(105, '20111', '84722039000', '2025-01-17 00:00:00', 12.41, 'Katharina Reicher', 'Restbetrag miete jaenner 2025 Katharina Reicher'),
(106, '20111', '84722039000', '2025-01-21 00:00:00', 228.00, 'Netz NOe GmbH', 'Rueckueberweisung Netzzutrittsentgelt Netz NOe GmbH'),
(107, '20111', '84722039000', '2025-01-21 00:00:00', 5279.87, 'FA Österreich - Weinviertel', 'RUECKZAHLUNG 16.01.2025 Immo-Fuchs FA Oesterreich - Weinviertel'),
(108, '20111', '84722039000', '2025-01-23 00:00:00', -167.42, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62602 EVN AG'),
(109, '20111', '84722039000', '2025-01-31 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(110, '20111', '84722039000', '2025-01-31 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(111, '20111', '84722039000', '2025-01-31 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(112, '20111', '84722039000', '2024-12-23 00:00:00', -122.55, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62701 EVN AG'),
(113, '20111', '84722039000', '2024-12-23 00:00:00', -172.55, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '304-1364026-6574729 Amazon.de 6FM6E AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(114, '20111', '84722039000', '2024-12-31 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(115, '20111', '84722039000', '2024-12-31 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(116, '20111', '84722039000', '2024-12-31 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(117, '20111', '84722039000', '2024-12-31 00:00:00', 0.00, 'unbekannt', '*** Abschlussbuchung per 31.12.2024 **** Reklamationen bitte binnen 2 Monaten'),
(118, '20111', '84722039000', '2024-12-31 00:00:00', 0.99, 'unbekannt', 'Habenzinsen'),
(119, '20111', '84722039000', '2024-12-31 00:00:00', -0.25, 'unbekannt', 'Kest'),
(120, '20111', '84722039000', '2024-12-31 00:00:00', -20.22, 'unbekannt', 'Kostenbeitrag Digital Banking'),
(121, '20111', '84722039000', '2024-12-31 00:00:00', -28.31, 'unbekannt', 'Kontofuehrung'),
(122, '20111', '84722039000', '2024-12-31 00:00:00', -7.35, 'unbekannt', 'Bereitstellung Debitkarte'),
(123, '20111', '84722039000', '2024-12-31 00:00:00', -26.09, 'unbekannt', 'Buchungskostenbeitrag'),
(124, '20111', '84722039000', '2024-12-02 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(125, '20111', '84722039000', '2024-12-02 00:00:00', 880.00, 'Katharina Reicher', 'Miete dezember 2024 Katharina Reicher'),
(126, '20111', '84722039000', '2024-12-02 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Dec 2024, Bahngasse 14 Anna Bondar'),
(127, '20111', '84722039000', '2024-12-03 00:00:00', -5654.51, 'Baustoff und Metall GmbH', 'Rg.Nr. 06-240602786 Restzahlung Baustoff und Metall GmbH'),
(128, '20111', '84722039000', '2024-12-03 00:00:00', 831.23, 'Petra Steinkogler', 'Miete Top4 Steinkogler Petra Steinkogler'),
(129, '20111', '84722039000', '2024-12-04 00:00:00', 40.80, 'Brigitte Greiner', 'Kfz-Stellplatz Nr. 2 Brigitte Greiner'),
(130, '20111', '84722039000', '2024-12-04 00:00:00', 1044.75, 'Brigitte Greiner', 'Miete Bahngasse 14/Top 3 Brigitte Greiner'),
(131, '20111', '84722039000', '2024-12-05 00:00:00', -322.48, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 34002 0041 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(132, '20111', '84722039000', '2024-12-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(133, '20111', '84722039000', '2024-12-12 00:00:00', -17054.45, 'Baierl GmbH', '250182338 Baierl GmbH'),
(134, '20111', '84722039000', '2024-12-13 00:00:00', 0.00, 'unbekannt', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx Beachten Sie bitte die neuen Zahlungsverkehrspreise'),
(135, '20111', '84722039000', '2024-11-04 00:00:00', -274.12, 'Baustoff und Metall GmbH', '262438605891 Baustoff und Metall GmbH'),
(136, '20111', '84722039000', '2024-11-04 00:00:00', -625.96, 'Gemeinde St. Andrä-Wördern', '008126002691 Gemeinde St. Andrae-Woerdern'),
(137, '20111', '84722039000', '2024-11-04 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(138, '20111', '84722039000', '2024-11-04 00:00:00', 831.23, 'Petra Steinkogler', 'Miete Top4 Steinkogler Petra Steinkogler'),
(139, '20111', '84722039000', '2024-11-04 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Nov 2024, Bahngasse 14 Anna Bondar'),
(140, '20111', '84722039000', '2024-11-05 00:00:00', 40.80, 'Brigitte Greiner', 'Kfz-Stellplatz Nr. 2 Brigitte Greiner'),
(141, '20111', '84722039000', '2024-11-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(142, '20111', '84722039000', '2024-11-05 00:00:00', 1044.75, 'Brigitte Greiner', 'Miete Bahngasse 14/Top 3 Brigitte Greiner'),
(143, '20111', '84722039000', '2024-11-06 00:00:00', -531.99, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 34002 0047 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(144, '20111', '84722039000', '2024-11-06 00:00:00', -967.44, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 34002 0041 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(145, '20111', '84722039000', '2024-11-18 00:00:00', -665.40, 'INTER-TREUHAND Prachner', '232745 251901 INTER-TREUHAND Prachner'),
(146, '20111', '84722039000', '2024-11-21 00:00:00', 7108.65, 'FA Österreich - Weinviertel', 'RUECKZAHLUNG 18.11.2024 Immo-Fuchs FA Oesterreich - Weinviertel'),
(147, '20111', '84722039000', '2024-11-25 00:00:00', -494.80, 'Lemp Energietechnik KG', 'Re.Nr.: 244417 Lemp Energietechnik KG'),
(148, '20111', '84722039000', '2024-11-26 00:00:00', -54.15, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62002 EVN AG'),
(149, '20111', '84722039000', '2024-11-29 00:00:00', -11.83, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(150, '20111', '84722039000', '2024-11-29 00:00:00', -200.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(151, '20111', '84722039000', '2024-11-29 00:00:00', -333.33, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(152, '20111', '84722039000', '2024-10-01 00:00:00', -1617.31, 'Lagerhaus', '245258130153 Lagerhaus'),
(153, '20111', '84722039000', '2024-10-02 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(154, '20111', '84722039000', '2024-10-02 00:00:00', 880.00, 'Katharina Reicher', 'Miete okt24 Katharina Reicher'),
(155, '20111', '84722039000', '2024-10-02 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Okt 2024, Bahngasse 14 Anna Bondar'),
(156, '20111', '84722039000', '2024-10-03 00:00:00', 831.23, 'Petra Steinkogler', 'Miete Top4 Steinkogler Petra Steinkogler'),
(157, '20111', '84722039000', '2024-10-04 00:00:00', 40.80, 'Brigitte Greiner', 'Kfz-Stellplatz Nr. 2 Brigitte Greiner'),
(158, '20111', '84722039000', '2024-10-04 00:00:00', 1044.75, 'Brigitte Greiner', 'Miete Bahngasse 14/Top 3 Brigitte Greiner'),
(159, '20111', '84722039000', '2024-10-07 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(160, '20111', '84722039000', '2024-10-09 00:00:00', -15.29, 'Frieda Fuchs', 'Hausmeister Reinigungsutensilien Frieda Fuchs'),
(161, '20111', '84722039000', '2024-10-09 00:00:00', -6000.00, 'Baustoff und Metall GmbH', 'Teilzahlung 06-240602786 Baustoff und Metall GmbH'),
(162, '20111', '84722039000', '2024-10-10 00:00:00', -314.56, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 34002 0047 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(163, '20111', '84722039000', '2024-10-14 00:00:00', -1240.76, 'MyLemon', 'A976912 MyLemon'),
(164, '20111', '84722039000', '2024-10-14 00:00:00', -30000.00, 'Martina Fuchs', 'Sparen Martina Fuchs'),
(165, '20111', '84722039000', '2024-10-16 00:00:00', -1616.51, 'Friedrich Preitensteiner Handels Ge', 'AR 241341 Friedrich Preitensteiner Handels Ge'),
(166, '20111', '84722039000', '2024-10-21 00:00:00', -1300.37, 'Schneider Dach GmbH', '24-202 Schneider Dach GmbH'),
(167, '20111', '84722039000', '2024-10-30 00:00:00', -832.20, 'Markisenland e.U.', '2024-019 Markisenland e.U.'),
(168, '20111', '84722039000', '2024-10-30 00:00:00', 880.00, 'Katharina Reicher', 'Miete november 24 Katharina Reicher'),
(169, '20111', '84722039000', '2024-10-31 00:00:00', -0.56, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62001 EVN AG'),
(170, '20111', '84722039000', '2024-10-31 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(171, '20111', '84722039000', '2024-10-31 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(172, '20111', '84722039000', '2024-10-31 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(173, '20111', '84722039000', '2024-09-02 00:00:00', -117.54, 'Baustoff und Metall GmbH', '06-240604485 Baustoff und Metall GmbH'),
(174, '20111', '84722039000', '2024-09-03 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(175, '20111', '84722039000', '2024-09-03 00:00:00', 831.23, 'Petra Steinkogler', 'Miete Top4 Steinkogler Petra Steinkogler'),
(176, '20111', '84722039000', '2024-09-03 00:00:00', 880.00, 'Katharina Reicher', 'Miete sep. 24 Katharina Reicher'),
(177, '20111', '84722039000', '2024-09-03 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Sep 2024, Bahngasse 14 Anna Bondar'),
(178, '20111', '84722039000', '2024-09-04 00:00:00', 40.80, 'Brigitte Greiner', 'Kfz-Stellplatz Nr. 2 Brigitte Greiner'),
(179, '20111', '84722039000', '2024-09-04 00:00:00', 1044.75, 'Brigitte Greiner', 'Miete Bahngasse 14/Top 3 Brigitte Greiner'),
(180, '20111', '84722039000', '2024-09-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(181, '20111', '84722039000', '2024-09-06 00:00:00', -3938.56, 'Baustoff und Metall GmbH', 'Rest zu 06-230606604 Baustoff und Metall GmbH'),
(182, '20111', '84722039000', '2024-09-10 00:00:00', -174.00, 'ING. T. FRIEBERGER INSTALLATIONEN', 'ReNr: 24536 ING. T. FRIEBERGER INSTALLATIONEN'),
(183, '20111', '84722039000', '2024-09-10 00:00:00', -832.20, 'Markisenland e.U.', 'Anzahlung Markise Bahngasse 14 in Markisenland e.U.'),
(184, '20111', '84722039000', '2024-09-13 00:00:00', 68901.13, 'FA Österreich - Weinviertel', 'RUECKZAHLUNG 10.09.2024 Immo-Fuchs FA Oesterreich - Weinviertel'),
(185, '20111', '84722039000', '2024-09-19 00:00:00', -55.62, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '028-7630519-7865935 Amazon.de 36V4X AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(186, '20111', '84722039000', '2024-09-19 00:00:00', -314.56, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'Saldo RV: 34002 0047 002 WEG 3423 St. Andrae-Woerdern, Lehne'),
(187, '20111', '84722039000', '2024-09-20 00:00:00', -5.00, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '028-7630519-7865935 Amazon.de 2FZBN AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(188, '20111', '84722039000', '2024-09-20 00:00:00', -7.14, 'AMAZON PAYMENTS EUROPE S.C.A.', '028-7498506-7601924 AMZN Mktp DE 3Y AMAZON PAYMENTS EUROPE S.C.A.'),
(189, '20111', '84722039000', '2024-09-20 00:00:00', -754.90, 'Praskac', 'Re: 84043 Praskac'),
(190, '20111', '84722039000', '2024-09-24 00:00:00', -890.00, 'EVN AG', '30684391 StAndrae-Woerdern,Bahngasse1 EVN AG'),
(191, '20111', '84722039000', '2024-09-24 00:00:00', 54.17, 'EVN AG', '31203090 3423 Bahngasse 14 ABR60098 EVN AG'),
(192, '20111', '84722039000', '2024-09-24 00:00:00', 58.18, 'EVN AG', '31203642 3423 Bahngasse 14 ABR60098 EVN AG'),
(193, '20111', '84722039000', '2024-09-24 00:00:00', 72.88, 'EVN AG', '31203166 3423 Bahngasse 14 ABR60098 EVN AG'),
(194, '20111', '84722039000', '2024-09-24 00:00:00', 78.75, 'EVN AG', '31203088 3423 Bahngasse 14 ABR60098 EVN AG'),
(195, '20111', '84722039000', '2024-09-30 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(196, '20111', '84722039000', '2024-09-30 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(197, '20111', '84722039000', '2024-09-30 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(198, '20111', '84722039000', '2024-09-30 00:00:00', 0.00, 'unbekannt', '*** Abschlussbuchung per 30.09.2024 **** Reklamationen bitte binnen 2 Monaten'),
(199, '20111', '84722039000', '2024-09-30 00:00:00', 0.46, 'unbekannt', 'Habenzinsen'),
(200, '20111', '84722039000', '2024-09-30 00:00:00', -0.12, 'unbekannt', 'Kest'),
(201, '20111', '84722039000', '2024-09-30 00:00:00', -20.22, 'unbekannt', 'Kostenbeitrag Digital Banking'),
(202, '20111', '84722039000', '2024-09-30 00:00:00', -42.75, 'unbekannt', 'Kontofuehrung'),
(203, '20111', '84722039000', '2024-09-30 00:00:00', -7.35, 'unbekannt', 'Bereitstellung Debitkarte'),
(204, '20111', '84722039000', '2024-09-30 00:00:00', -32.73, 'unbekannt', 'Buchungskostenbeitrag'),
(205, '20111', '84722039000', '2024-08-01 00:00:00', -25.98, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '305-3931752-7267548 Amazon.de 4ZDM2 AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(206, '20111', '84722039000', '2024-08-01 00:00:00', -800.00, 'Preitensteiner', 'AR 240968 Preitensteiner'),
(207, '20111', '84722039000', '2024-08-02 00:00:00', -2448.00, 'ARS Akademie', '82406733 ARS Akademie'),
(208, '20111', '84722039000', '2024-08-02 00:00:00', 4000.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(209, '20111', '84722039000', '2024-08-05 00:00:00', -186.00, 'maluk GmbH', 'YYMCFXZWB maluk GmbH'),
(210, '20111', '84722039000', '2024-08-05 00:00:00', -578.63, 'Gemeinde St. Andrä-Wördern', '008081002716 Gemeinde St. Andrae-Woerdern'),
(211, '20111', '84722039000', '2024-08-05 00:00:00', -2448.00, 'ARS Akademie', '82406733 ARS Akademie'),
(212, '20111', '84722039000', '2024-08-05 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(213, '20111', '84722039000', '2024-08-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(214, '20111', '84722039000', '2024-08-05 00:00:00', 831.23, 'Petra Steinkogler', 'Miete Top4 Steinkogler Petra Steinkogler'),
(215, '20111', '84722039000', '2024-08-05 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, August 2024, Bahngasse Anna Bondar'),
(216, '20111', '84722039000', '2024-08-06 00:00:00', 40.80, 'Brigitte Greiner', 'Kfz-Stellplatz Nr. 2 Brigitte Greiner'),
(217, '20111', '84722039000', '2024-08-06 00:00:00', 1044.75, 'Brigitte Greiner', 'Miete Bahngasse 14/Top 3 Brigitte Greiner'),
(218, '20111', '84722039000', '2024-08-07 00:00:00', -217.00, 'Frieda Fuchs', 'BK Lehnergasse 2/6/5 Frieda Fuchs'),
(219, '20111', '84722039000', '2024-08-08 00:00:00', -33.60, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '303-1242854-2743553 Amazon.de 4CG5R AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(220, '20111', '84722039000', '2024-08-14 00:00:00', -609.60, 'Intertreuhand Prachner', '232745 250597 Intertreuhand Prachner'),
(221, '20111', '84722039000', '2024-08-19 00:00:00', -2400.00, 'Yunus Akca KG', 'Rechnung 242613 Yunus Akca KG'),
(222, '20111', '84722039000', '2024-08-18 00:00:00', 2000.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(223, '20111', '84722039000', '2024-08-18 00:00:00', 4000.00, 'Thomas Fuchs', 'Eigenuebertrag Thomas Fuchs'),
(224, '20111', '84722039000', '2024-08-22 00:00:00', 2448.00, 'ARS Seminar und Kongreß', 'Rueckueberweisung DZ 82406733 ARS Seminar und Kongress'),
(225, '20111', '84722039000', '2024-08-30 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(226, '20111', '84722039000', '2024-08-30 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt 08.2024 Frieda Fuchs'),
(227, '20111', '84722039000', '2024-08-30 00:00:00', -200.00, 'Eric Fuchs', 'Gehalt 08.2024 Eric Fuchs'),
(228, '20111', '84722039000', '2024-07-02 00:00:00', -9.80, 'AMAZON PAYMENTS EUROPE S.C.A.', '305-3492109-1728353 AMZN Mktp DE 2A AMAZON PAYMENTS EUROPE S.C.A.'),
(229, '20111', '84722039000', '2024-07-02 00:00:00', -860.40, 'L&E Feuerlöschtechnik OG', 'Re.Nr.: 2400380 L&amp;E Feuerloeschtechnik OG'),
(230, '20111', '84722039000', '2024-07-02 00:00:00', 40.80, 'BRIGITTE GREINER', 'RE10 2024 BAHNG 14 KFZSTELLPL NR2? BRIGITTE GREINER'),
(231, '20111', '84722039000', '2024-07-02 00:00:00', 1044.75, 'BRIGITTE GREINER', '- BRIGITTE GREINER'),
(232, '20111', '84722039000', '2024-07-03 00:00:00', -21.00, 'AMAZON PAYMENTS EUROPE S.C.A.', '305-3492109-1728353 AMZN Mktp DE 6A AMAZON PAYMENTS EUROPE S.C.A.'),
(233, '20111', '84722039000', '2024-07-03 00:00:00', -31.92, 'AMAZON PAYMENTS EUROPE S.C.A.', '305-3492109-1728353 AMZN Mktp DE IW AMAZON PAYMENTS EUROPE S.C.A.'),
(234, '20111', '84722039000', '2024-07-03 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(235, '20111', '84722039000', '2024-07-03 00:00:00', 831.23, 'Petra Steinkogler', 'Miete Top4 Steinkogler Petra Steinkogler'),
(236, '20111', '84722039000', '2024-07-03 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, July 2024, Bahngasse 1 Anna Bondar'),
(237, '20111', '84722039000', '2024-07-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(238, '20111', '84722039000', '2024-07-05 00:00:00', 20000.00, 'Thomas Fuchs', 'Einlage Thomas Fuchs'),
(239, '20111', '84722039000', '2024-07-10 00:00:00', -73.44, 'Finanzamt für Gebühren', '105159305 Finanzamt fuer Gebuehren'),
(240, '20111', '84722039000', '2024-07-10 00:00:00', -27909.22, 'Lemp Energietechnik KG', 'SR Nr. 242686 Sanitaer Heinze Lemp Energietechnik KG'),
(241, '20111', '84722039000', '2024-07-09 00:00:00', 10000.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(242, '20111', '84722039000', '2024-07-22 00:00:00', -103.30, 'Gemeinde St. Andrä-Wördern', 'F791813 Gemeinde St. Andrae-Woerdern'),
(243, '20111', '84722039000', '2024-07-22 00:00:00', -549.00, 'AMAZON PAYMENTS EUROPE S.C.A.', 'P02-2582039-6911180 amzn.com/pmts 5 AMAZON PAYMENTS EUROPE S.C.A.'),
(244, '20111', '84722039000', '2024-07-22 00:00:00', -2197.89, 'BRT Bau GmbH', 'Rg.Nr. BRT24045P BRT Bau GmbH'),
(245, '20111', '84722039000', '2024-07-29 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(246, '20111', '84722039000', '2024-07-29 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt 07.2024 Frieda Fuchs'),
(247, '20111', '84722039000', '2024-07-29 00:00:00', -200.00, 'Eric Fuchs', 'Gehalt 07.2024 Eric Fuchs'),
(248, '20111', '84722039000', '2024-07-29 00:00:00', -5177.65, 'Gemeinde St. Adnrä-Wördern', 'F791812 Gemeinde St. Adnrae-Woerdern'),
(249, '20111', '84722039000', '2024-06-03 00:00:00', -276.47, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '306-9310803-6906769 Amazon.de 511VA AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(250, '20111', '84722039000', '2024-06-03 00:00:00', -5647.68, 'EVN Niederösterreich GmbH', '30684392 EVN Niederoesterreich GmbH'),
(251, '20111', '84722039000', '2024-06-03 00:00:00', -7421.50, 'Svoboda', 'Re-Nr. 20241126 Svoboda'),
(252, '20111', '84722039000', '2024-06-03 00:00:00', 181.27, 'Petra Steinkogler', 'BK Juni 2024 Petra Steinkogler'),
(253, '20111', '84722039000', '2024-06-03 00:00:00', 227.83, 'BRIGITTE GREINER', '. BRIGITTE GREINER'),
(254, '20111', '84722039000', '2024-06-03 00:00:00', 81.60, 'Bogdan Bondar', 'Kfz-Stellplatz Nr. 5 und 6 Bogdan Bondar'),
(255, '20111', '84722039000', '2024-06-03 00:00:00', 227.92, 'Bogdan Bondar', 'Anna und Bogdan Bondar Bogdan Bondar'),
(256, '20111', '84722039000', '2024-06-05 00:00:00', -7628.62, 'Boden Karner GmbH', 'Re-Nr. 24-00209-RE Boden Karner GmbH'),
(257, '20111', '84722039000', '2024-06-05 00:00:00', -20733.98, 'Baustoff und Metall GmbH', 'Re-Nr: 06-240602591 Baustoff und Metall GmbH'),
(258, '20111', '84722039000', '2024-06-04 00:00:00', 32000.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(259, '20111', '84722039000', '2024-06-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(260, '20111', '84722039000', '2024-06-07 00:00:00', -228.00, 'EVN Niederösterreich GmbH', '31217883 EVN Niederoesterreich GmbH'),
(261, '20111', '84722039000', '2024-06-10 00:00:00', -252.78, 'EVN Niederösterreich GmbH', '31217883 EVN Niederoesterreich GmbH'),
(262, '20111', '84722039000', '2024-06-10 00:00:00', 74691.57, 'FA Österreich - Weinviertel', 'RUECKZAHLUNG 05.06.2024 Immo-Fuchs FA Oesterreich - Weinviertel'),
(263, '20111', '84722039000', '2024-06-12 00:00:00', -19003.02, 'Andreas Eder, Fliesenlegermeister', 'Rg.Nr. 2024047 Andreas Eder, Fliesenlegermeister'),
(264, '20111', '84722039000', '2024-06-17 00:00:00', -2.20, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(265, '20111', '84722039000', '2024-06-17 00:00:00', -276.47, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '304-7089446-7303561 Amazon.de 16Y8E AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(266, '20111', '84722039000', '2024-06-17 00:00:00', -25220.51, 'BRT Bau GmbH', 'Rg.Nr. BRT24036A BRT Bau GmbH'),
(267, '20111', '84722039000', '2024-06-17 00:00:00', -32490.00, 'Ing. Baierl GmbH', '250180553 Ing. Baierl GmbH'),
(268, '20111', '84722039000', '2024-06-20 00:00:00', -15.13, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '304-7911973-0075523 Amazon.de 1PTK6 AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(269, '20111', '84722039000', '2024-06-20 00:00:00', -890.00, 'EVN AG', '30684391 StAndrae-Woerdern,Bahngasse1 EVN AG'),
(270, '20111', '84722039000', '2024-06-24 00:00:00', -2982.00, 'Waringer GmbH', 'Rg.Nr.: RE20240518 Waringer GmbH'),
(271, '20111', '84722039000', '2024-06-24 00:00:00', -24009.60, 'Leeb Balkone GmbH', 'Rg.Nr. 576570 Leeb Balkone GmbH'),
(272, '20111', '84722039000', '2024-06-23 00:00:00', 72900.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(273, '20111', '84722039000', '2024-06-26 00:00:00', -11.67, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(274, '20111', '84722039000', '2024-06-26 00:00:00', -200.00, 'Frieda Fuchs', 'Gehalt 06.2024 inkl. UZ Frieda Fuchs'),
(275, '20111', '84722039000', '2024-06-26 00:00:00', -333.33, 'Eric Fuchs', 'Gehalt 06.2024 inkl. UZ Eric Fuchs'),
(276, '20111', '84722039000', '2024-06-26 00:00:00', -50000.00, 'Thomas Fuchs', 'Lehnergasse Thomas Fuchs'),
(277, '20111', '84722039000', '2024-06-30 00:00:00', 0.00, 'unbekannt', '*** Abschlussbuchung per 30.06.2024 **** Reklamationen bitte binnen 2 Monaten'),
(278, '20111', '84722039000', '2024-06-30 00:00:00', 1.25, 'unbekannt', 'Habenzinsen'),
(279, '20111', '84722039000', '2024-06-30 00:00:00', -0.31, 'unbekannt', 'Kest'),
(280, '20111', '84722039000', '2024-06-30 00:00:00', -20.22, 'unbekannt', 'Kostenbeitrag Digital Banking'),
(281, '20111', '84722039000', '2024-06-30 00:00:00', -167.45, 'unbekannt', 'Kontofuehrung'),
(282, '20111', '84722039000', '2024-06-30 00:00:00', -6.81, 'unbekannt', 'Bereitstellung Debitkarte'),
(283, '20111', '84722039000', '2024-06-30 00:00:00', -32.73, 'unbekannt', 'Buchungskostenbeitrag'),
(284, '20111', '84722039000', '2024-05-06 00:00:00', -53.99, 'AMAZON MEDIA EU S.A R.L.', 'D01-8394598-0712613 AMZN Digital 2H AMAZON MEDIA EU S.A R.L.'),
(285, '20111', '84722039000', '2024-05-07 00:00:00', -13065.55, 'Waringer GmbH', 'Rg.Nr: RE20240339 Waringer GmbH'),
(286, '20111', '84722039000', '2024-05-10 00:00:00', -7040.99, 'Baustoff und Metall GmbH', '06-240602152 Baustoff und Metall GmbH'),
(287, '20111', '84722039000', '2024-05-10 00:00:00', -7442.40, 'Baustoff und Metall GmbH', '06-240602151 Baustoff und Metall GmbH'),
(288, '20111', '84722039000', '2024-05-13 00:00:00', -258.00, 'Intertreuhand Prachner', '232745 244032 Intertreuhand Prachner'),
(289, '20111', '84722039000', '2024-05-13 00:00:00', -3397.38, 'Christoph Tille', 'Rg-Nr. 2024/180 Christoph Tille'),
(290, '20111', '84722039000', '2024-05-13 00:00:00', -49322.18, 'BRT Bau GmbH', 'Rg.Nr.: BRT24025A BRT Bau GmbH'),
(291, '20111', '84722039000', '2024-05-17 00:00:00', -120.00, 'EVN Niederösterreich GmbH', '20791868 EVN Niederoesterreich GmbH'),
(292, '20111', '84722039000', '2024-05-22 00:00:00', 15000.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(293, '20111', '84722039000', '2024-05-23 00:00:00', -12.60, 'AMAZON PAYMENTS EUROPE S.C.A.', '028-8637764-5250743 AMZN Mktp DE 13 AMAZON PAYMENTS EUROPE S.C.A.'),
(294, '20111', '84722039000', '2024-05-23 00:00:00', -27.72, 'AMAZON PAYMENTS EUROPE S.C.A.', '028-8637764-5250743 AMZN Mktp DE 5E AMAZON PAYMENTS EUROPE S.C.A.'),
(295, '20111', '84722039000', '2024-05-23 00:00:00', -62.17, 'AMAZON PAYMENTS EUROPE S.C.A.', '028-8637764-5250743 AMZN Mktp DE 1P AMAZON PAYMENTS EUROPE S.C.A.'),
(296, '20111', '84722039000', '2024-05-23 00:00:00', -100.00, 'EVN AG', '31203090 EVN AG'),
(297, '20111', '84722039000', '2024-05-23 00:00:00', -100.00, 'EVN AG', '31203166 EVN AG'),
(298, '20111', '84722039000', '2024-05-23 00:00:00', -100.00, 'EVN AG', '31203642 EVN AG'),
(299, '20111', '84722039000', '2024-05-23 00:00:00', -100.00, 'EVN AG', '31203088 EVN AG'),
(300, '20111', '84722039000', '2024-05-23 00:00:00', -828.00, 'Svoboda', 'Teilrechnung 241008-1 Svoboda'),
(301, '20111', '84722039000', '2024-05-24 00:00:00', 27431.58, 'Frieda Fuchs', 'SEPA-Gutschrift Frieda Fuchs'),
(302, '20111', '84722039000', '2024-05-27 00:00:00', -2203.69, 'Lemp Energietechnik KG', 'Re-Nr. 242052 Lemp Energietechnik KG'),
(303, '20111', '84722039000', '2024-05-27 00:00:00', -3173.71, 'Raiffeisen Factor Bank, Eigner & Ro', 'Re-Nr. 202400203 Raiffeisen Factor Bank, Eigner &amp; Ro'),
(304, '20111', '84722039000', '2024-05-29 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt 05.2024 Frieda Fuchs'),
(305, '20111', '84722039000', '2024-05-29 00:00:00', -200.00, 'Eric Fuchs', 'Gehalt 05.2024 Eric Fuchs'),
(306, '20111', '84722039000', '2024-05-29 00:00:00', -13700.00, 'Yunus Akca KG', 'Re-Nr. 242555 Yunus Akca KG'),
(307, '20111', '84722039000', '2024-04-08 00:00:00', -407.22, 'Baustoff und Metall GmbH', '262438601603 Baustoff und Metall GmbH'),
(308, '20111', '84722039000', '2024-04-08 00:00:00', 100000.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(309, '20111', '84722039000', '2024-04-09 00:00:00', -66799.98, 'BRT Bau GmbH', 'BRT24015A BRT Bau GmbH'),
(310, '20111', '84722039000', '2024-04-10 00:00:00', -4693.78, 'Raiffeisen Factor Bank, Eigner & Ro', 'Rg.-Nr. 202301967 Raiffeisen Factor Bank, Eigner &amp; Ro'),
(311, '20111', '84722039000', '2024-04-11 00:00:00', -1109.87, 'Raiffeisen Factor Bank, Eigner & Ro', 'Rg.Nr. 202301966 Raiffeisen Factor Bank, Eigner &amp; Ro'),
(312, '20111', '84722039000', '2024-04-15 00:00:00', -2528.01, 'Christoph Tille', '2024/130 Christoph Tille'),
(313, '20111', '84722039000', '2024-04-15 00:00:00', -2829.00, 'Helvetia Versicherungen AG', '2416093953/POL 4002544175 4/2024 HE Helvetia Versicherungen AG'),
(314, '20111', '84722039000', '2024-04-15 00:00:00', -18000.00, 'Andreas Eder, Fliesenlegermeister', 'Rg.Nr. 2024031 Andreas Eder, Fliesenlegermeister'),
(315, '20111', '84722039000', '2024-04-15 00:00:00', -22500.00, 'Leeb Balkone GmbH', 'Rg.Nr. 575040 Leeb Balkone GmbH'),
(316, '20111', '84722039000', '2024-04-15 00:00:00', -35329.34, 'Baierl GmbH', '240184012 Baierl GmbH'),
(317, '20111', '84722039000', '2024-04-17 00:00:00', -7391.40, 'Schneider Dach GmbH', 'Rg.Nr. 24-051 Schneider Dach GmbH'),
(318, '20111', '84722039000', '2024-04-16 00:00:00', 100000.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(319, '20111', '84722039000', '2024-04-22 00:00:00', -1560.69, 'Baustoff und Metall GmbH', '262438601896 Baustoff und Metall GmbH'),
(320, '20111', '84722039000', '2024-04-22 00:00:00', -2371.32, 'Raiffeisen Factor Bank, Eigner & Ro', '202400030 Raiffeisen Factor Bank, Eigner &amp; Ro'),
(321, '20111', '84722039000', '2024-04-22 00:00:00', -12687.60, 'K & E GmbH, Maler', '2024-071 K &amp; E GmbH, Maler'),
(322, '20111', '84722039000', '2024-04-24 00:00:00', -722.68, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '306-1814441-4751504 Amazon.de 2MJ84 AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(323, '20111', '84722039000', '2024-04-25 00:00:00', -12.61, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '306-1089548-7714718 Amazon.de 3LP9H AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(324, '20111', '84722039000', '2024-04-30 00:00:00', -421.82, 'Gemeinde St. Adnrä-Wördern', '008039003165 Gemeinde St. Adnrae-Woerdern'),
(325, '20111', '84722039000', '2024-03-06 00:00:00', -31000.00, 'Yunus Akca KG', 'Re: 242498 Yunus Akca KG'),
(326, '20111', '84722039000', '2024-03-08 00:00:00', -23280.00, 'Schneider Dach GmbH', '2. TR, Re-Nr. 24-026 Schneider Dach GmbH'),
(327, '20111', '84722039000', '2024-03-11 00:00:00', -16.85, 'AMAZON PAYMENTS EUROPE S.C.A.', '304-5834174-4643508 AMZN Mktp DE 4N AMAZON PAYMENTS EUROPE S.C.A.'),
(328, '20111', '84722039000', '2024-03-11 00:00:00', -180.00, 'Grasl clever Immobilien KG', 'RECHNUNG Nr. G 278 Grasl clever Immobilien KG'),
(329, '20111', '84722039000', '2024-03-11 00:00:00', -72250.18, 'BRT Bau GmbH', 'Rg.Nr. BRT24008A BRT Bau GmbH'),
(330, '20111', '84722039000', '2024-03-09 00:00:00', 200000.00, 'Martina Fuchs', 'Eigenuebertrag Martina Fuchs'),
(331, '20111', '84722039000', '2024-03-12 00:00:00', -8.92, 'AMAZON PAYMENTS EUROPE S.C.A.', '304-5834174-4643508 AMZN Mktp DE 6F AMAZON PAYMENTS EUROPE S.C.A.'),
(332, '20111', '84722039000', '2024-03-12 00:00:00', -91.60, 'AMAZON PAYMENTS EUROPE S.C.A.', '304-5834174-4643508 AMZN Mktp DE 5D AMAZON PAYMENTS EUROPE S.C.A.'),
(333, '20111', '84722039000', '2024-03-13 00:00:00', -18000.00, 'Andreas Eder, Fliesenlegermeister', 'Rechnung 2024022 Andreas Eder, Fliesenlegermeister'),
(334, '20111', '84722039000', '2024-03-18 00:00:00', -9312.00, 'K & E GmbH, Maler', '1. TR Nr. 2024-043 K &amp; E GmbH, Maler'),
(335, '20111', '84722039000', '2024-03-18 00:00:00', -31994.60, 'Lemp Energietechnik KG', 'SR Nr. 241152 Lemp Energietechnik KG'),
(336, '20111', '84722039000', '2024-03-19 00:00:00', -929.37, 'ZIEGLER Außenanlagen GmbH', 'AZR02278 ZIEGLER Aussenanlagen GmbH'),
(337, '20111', '84722039000', '2024-03-19 00:00:00', -4523.66, 'Porr Bau GmbH', 'PQ24502658 Porr Bau GmbH'),
(338, '20111', '84722039000', '2024-03-21 00:00:00', -520.80, 'Karl Löschl GesmbH', 'Re-Nr.: 20240284 Karl Loeschl GesmbH'),
(339, '20111', '84722039000', '2024-03-22 00:00:00', -69.75, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '304-2514161-3994713 Amazon.de 2JC17 AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(340, '20111', '84722039000', '2024-03-22 00:00:00', -83.98, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '304-2514161-3994713 Amazon.de 1GLG6 AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(341, '20111', '84722039000', '2024-03-22 00:00:00', -95.78, 'AMAZON EU S.A R.L., NIEDERLASSUNG D', '304-2514161-3994713 Amazon.de SIQA6 AMAZON EU S.A R.L., NIEDERLASSUNG D'),
(342, '20111', '84722039000', '2024-03-25 00:00:00', -1100.00, 'Trend-Master', '210404 Trend-Master'),
(343, '20111', '84722039000', '2024-03-27 00:00:00', -25820.66, 'Schneider Dach GmbH', 'Rg.Nr. 24-030 Schneider Dach GmbH'),
(344, '20111', '84722039000', '2024-03-31 00:00:00', 0.00, 'unbekannt', '*** Abschlussbuchung per 31.03.2024 **** Reklamationen bitte binnen 2 Monaten'),
(345, '20111', '84722039000', '2024-03-31 00:00:00', 3.57, 'unbekannt', 'Habenzinsen'),
(346, '20111', '84722039000', '2024-03-31 00:00:00', -0.89, 'unbekannt', 'Kest'),
(347, '20111', '84722039000', '2024-03-31 00:00:00', -20.22, 'unbekannt', 'Kostenbeitrag Digital Banking'),
(348, '20111', '84722039000', '2024-03-31 00:00:00', -154.83, 'unbekannt', 'Kontofuehrung'),
(349, '20111', '84722039000', '2024-03-31 00:00:00', -6.81, 'unbekannt', 'Bereitstellung Debitkarte'),
(350, '20111', '84722039000', '2024-03-31 00:00:00', -17.43, 'unbekannt', 'Buchungskostenbeitrag'),
(351, '20111', '84722039000', '2024-02-02 00:00:00', -453.44, 'Gemeinde St. Adnrä-Wördern', '007994002977 Gemeinde St. Adnrae-Woerdern'),
(352, '20111', '84722039000', '2024-02-06 00:00:00', -52778.73, 'BRT Bau GmbH', 'BRT24004A BRT Bau GmbH'),
(353, '20111', '84722039000', '2024-02-13 00:00:00', -14994.00, 'Lemp Energietechnik KG', '4. TR, Rg-Nr. 240651 Lemp Energietechnik KG'),
(354, '20111', '84722039000', '2024-02-13 00:00:00', -32319.00, 'Ing. Baierl GmbH', '2. TR, Rg-Nr. 240183195 Ing. Baierl GmbH'),
(355, '20111', '84722039000', '2024-02-16 00:00:00', -224.40, 'Intertreuhand Prachner', '232745 242949 Intertreuhand Prachner'),
(356, '20111', '84722039000', '2024-02-20 00:00:00', -2729.11, 'EVN AG', '30684391 StAndrae-Woerdern,Bahngasse1 EVN AG'),
(357, '20111', '84722039000', '2024-02-20 00:00:00', -24811.36, 'BRT Bau GmbH', 'Re-Nr. BRT24006A BRT Bau GmbH'),
(358, '20111', '84722039000', '2024-02-21 00:00:00', -23280.00, 'Schneider Dach GmbH', '1. TR, Rg.Nr. 24-013 Schneider Dach GmbH'),
(359, '20111', '84722039000', '2024-02-23 00:00:00', 56512.16, 'FA Österreich - Weinviertel', 'RUECKZAHLUNG 20.02.2024 Immo-Fuchs FA Oesterreich - Weinviertel'),
(360, '20111', '84722039000', '2024-02-27 00:00:00', -6451.94, 'Baustoff und Metall GmbH', '262438607001 Baustoff und Metall GmbH'),
(361, '20111', '84722039000', '2024-02-28 00:00:00', -3170.40, 'Baustoff und Metall GmbH', '262438600842 Baustoff und Metall GmbH'),
(362, '20111', '84722039000', '2024-01-05 00:00:00', -16.72, 'AMAZON PAYMENTS EUROPE S.C.A.', '305-8982894-2853111 AMZN Mktp DE 29 AMAZON PAYMENTS EUROPE S.C.A.'),
(363, '20111', '84722039000', '2024-01-08 00:00:00', -289.84, 'Raiffeisen Factor Bank, Eigner & Ro', 'Re-Nr. 202301640 Raiffeisen Factor Bank, Eigner &amp; Ro'),
(364, '20111', '84722039000', '2024-01-15 00:00:00', -8731.80, 'Lemp Energietechnik KG', '3. TR, Rg.Nr. 240138 Lemp Energietechnik KG'),
(365, '20111', '84722039000', '2024-01-15 00:00:00', -52624.20, 'BRT Bau GmbH', 'Rg.Nr. BRT24001A BRT Bau GmbH'),
(366, '20111', '84722039000', '2024-01-17 00:00:00', 0.00, 'unbekannt', 'Guthaben auf Girokonten und Spareinlagen sind gemaess Einlagensicherungs- und'),
(367, '20111', '84722039000', '2024-01-22 00:00:00', -222.00, 'Intertreuhand Prachner', '232745 241724 Intertreuhand Prachner'),
(368, '20111', '84722039000', '2025-07-01 00:00:00', 27.04, 'Frieda Fuchs', 'Abrechnung Top 1, Fuchs Frieda 2024 Frieda Fuchs'),
(369, '20111', '84722039000', '2025-07-01 00:00:00', 892.41, 'Katharina Reicher', 'Miete juni 2025 Katharina Reicher'),
(370, '20111', '84722039000', '2025-07-03 00:00:00', 81.60, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(371, '20111', '84722039000', '2025-07-03 00:00:00', 831.23, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(372, '20111', '84722039000', '2025-07-03 00:00:00', 1045.14, 'Anna Bondar', 'Mietvertrag, Juli 2025, Bahngasse 1 Anna Bondar'),
(373, '20111', '84722039000', '2025-07-04 00:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Lehne', '022520047003 WEG 3423 St. Andrae-Woerdern, Lehne'),
(374, '20111', '84722039000', '2025-07-04 00:00:00', 40.80, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(375, '20111', '84722039000', '2025-07-06 00:00:00', -40000.00, 'Thomas Fuchs', 'Privat Thomas Fuchs'),
(376, '20111', '84722039000', '2025-07-07 00:00:00', 11.90, 'Anna Bondar', 'Indexanpassung Parkplatz 5-6 Bondar Anna Bondar'),
(377, '20111', '84722039000', '2025-07-07 00:00:00', 94.55, 'Petra Steinkogler', 'nachverrechnung wertsicherung top 4 Petra Steinkogler'),
(378, '20111', '84722039000', '2025-07-07 00:00:00', 118.85, 'Anna Bondar', 'Wertsicherung Top 2 Bondar Anna Bondar'),
(379, '20111', '84722039000', '2025-07-07 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(380, '20111', '84722039000', '2025-07-07 00:00:00', 218.31, 'Anna Bondar', 'BK-Abrechnung Top 2, Bondar Anna Bondar'),
(381, '20111', '84722039000', '2025-07-07 00:00:00', 1044.75, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(382, '20111', '84722039000', '2025-07-09 00:00:00', -51.99, 'AMAZON MEDIA EU S.A R.L.', 'D01-7736393-1307803 AMZN Digital 3G AMAZON MEDIA EU S.A R.L.'),
(383, '20111', '84722039000', '2025-07-14 00:00:00', 49.02, 'Petra Steinkogler', 'BK Nachzahlung Abrechnung 2024 Petra Steinkogler'),
(384, '20111', '84722039000', '2025-07-21 00:00:00', -178.19, 'Tamara Pieringer', 'Gardena Wand-Schlauchbox rollup Tamara Pieringer'),
(385, '20111', '84722039000', '2025-07-22 00:00:00', -44.25, 'EVN AG', '30684391 3423 Bahngasse 14 ABR62605 EVN AG'),
(386, '20111', '84722039000', '2025-07-31 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(387, '20111', '84722039000', '2025-07-31 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(388, '20111', '84722039000', '2025-07-31 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(441, '11000', 'AT171100009393949400', '2025-08-08 10:00:00', -468.00, 'INTER-TREUHAND Prachner', '260477'),
(442, '12000', 'AT161200000696212729', '2025-08-08 10:00:00', -15.00, 'Stadt Wien - MA 6-BA 40', '000209854656'),
(443, '60000', 'AT166000000093027131', '2025-08-05 10:00:00', -570.93, 'Gemeinde St. Andrä-Wördern', '008312002675'),
(444, 'GIBAATWWXXX', 'AT792011122612019300', '2025-08-05 10:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs'),
(445, 'RLNWATW1880', 'AT313288000007005994', '2025-08-05 10:00:00', 1068.52, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3'),
(446, 'RLNWATW1880', 'AT313288000007005994', '2025-08-05 10:00:00', 41.99, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2'),
(447, 'GIBAATWWXXX', 'AT472011184580265400', '2025-08-04 10:00:00', 83.98, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Juli 2025)'),
(448, 'GIBAATWWXXX', 'AT472011184580265400', '2025-08-04 10:00:00', 1068.91, 'Anna Bondar', 'Mietvertrag, Juli 2025, Bahngasse 1 4/Top 2'),
(449, 'RZOOAT2L380', 'AT343438000006222343', '2025-08-04 10:00:00', 850.11, 'Steinkogler  Petra', 'Miete Top4 Steinkogler'),
(450, 'VBOEATWWXXX', 'AT824300000005702303', '2025-08-04 10:00:00', 118.85, 'Mag. Tamara Pieringer', 'Nachverrechnung'),
(451, '32000', 'AT863200052909318320', '2025-08-04 10:00:00', -260.68, 'WEG 3423 St. Andrae-Woerdern, Le', '02252 0047 003'),
(452, '11000', 'AT171100009393949400', '2025-08-01 10:00:00', -516.00, 'INTER-TREUHAND Prachner', '254387'),
(453, 'BKAUATWWXXX', 'AT501200010013537708', '2025-08-01 10:00:00', 892.41, 'Katharina Reicher', 'Miete juli 2025'),
(467, '20111', '84722039000', '2025-08-13 00:00:00', -5533.14, 'FA Tulln', '223849191 FA Tulln'),
(468, '20111', '84722039000', '2025-08-14 00:00:00', -350.00, 'Mag. Isabella Pouzar-Hofmeister', 'RNr. 523/25 Mag. Isabella Pouzar-Hofmeister'),
(469, '20111', '84722039000', '2025-08-15 00:00:00', -378.14, 'AMAZON PAYMENTS EUROPE S.C.A.', '304-5016229-0930757 AMZN Mktp DE 6S AMAZON PAYMENTS EUROPE S.C.A.'),
(470, '20111', '84722039000', '2025-08-27 00:00:00', -1351.40, 'K & E GmbH, Maler', '2025-126 K &amp; E GmbH, Maler');
INSERT INTO `auszuege` (`id`, `bankid`, `acctid`, `dtposted`, `betrag`, `name`, `memo`) VALUES
(471, '20111', '84722039000', '2025-08-29 00:00:00', -7.10, 'ÖGK NÖ', 'Beitr.KtoNr.: 065015757 OeGK NOe'),
(472, '20111', '84722039000', '2025-08-29 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(473, '20111', '84722039000', '2025-08-29 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(474, '01234', 'AT351200000913055984', '2025-09-10 10:00:00', -369.48, 'Petra Auenheimer', 'VS 09/2025, Meidlinger Hauptstr.69/ Top5'),
(475, '01234', 'AT792011122612019300', '2025-09-05 10:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs'),
(476, '01234', 'AT863200052909318320', '2025-09-04 10:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Le', '022520047003'),
(477, '01234', 'AT313288000007005994', '2025-09-04 10:00:00', 1068.52, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3'),
(478, '01234', 'AT313288000007005994', '2025-09-04 10:00:00', 41.99, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2'),
(479, '01234', 'AT343438000006222343', '2025-09-03 10:00:00', 850.11, 'Steinkogler  Petra', 'Miete Top4 Steinkogler'),
(480, '01234', '01234', '2025-09-02 10:00:00', 0.00, '', 'Aenderungen bei Ueberweisungen ab 9.10.25 XXX Es aendern sich 2 wichtige Punkte: Mehr Sicherheit durch Empfaenger-Ueberpruefung Vor Freigabe der Ueberweisung wird in Zukunft der Name und IBAN der Empfaenger:in mit der Empfaengerbank abgeglichen. Falls etw'),
(481, '01234', 'AT362011129711349000', '2025-09-02 10:00:00', 700.00, 'Jerica Steklasa', 'Miete - September 2025 (J. Steklasa , M .U. Chikwereuba), Meidlinger Ha upts trasse 69/1/5, 1120 Wien'),
(482, '01234', 'AT501200010013537708', '2025-09-02 10:00:00', 898.62, 'Katharina Reicher', 'Miete August 2025'),
(483, '01234', 'AT472011184580265400', '2025-09-01 10:00:00', 83.98, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Sep 2025)'),
(484, '01234', 'AT472011184580265400', '2025-09-01 10:00:00', 1068.91, 'Anna Bondar', 'Mietvertrag, Sep 2025, Bahngasse 14 /Top 2'),
(485, '20111', '84722039000', '2025-10-01 00:00:00', 898.62, 'Katharina Reicher', 'Miete September 2025 Katharina Reicher'),
(486, '20111', '84722039000', '2025-10-02 00:00:00', -2138.42, 'Hetsch & Paulinz RA', 'Honorarnote: 858/2025 Hetsch &amp; Paulinz RA'),
(487, '20111', '84722039000', '2025-10-02 00:00:00', 83.98, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(488, '20111', '84722039000', '2025-10-02 00:00:00', 1068.91, 'Anna Bondar', 'Mietvertrag, Okt 2025, Bahngasse 14 Anna Bondar'),
(489, '20111', '84722039000', '2025-10-03 00:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Lehne', '022520047003 WEG 3423 St. Andrae-Woerdern, Lehne'),
(490, '20111', '84722039000', '2025-10-03 00:00:00', 850.11, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(491, '20111', '84722039000', '2025-10-06 00:00:00', 41.99, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(492, '20111', '84722039000', '2025-10-06 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(493, '20111', '84722039000', '2025-10-06 00:00:00', 1068.52, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(494, '20111', '84722039000', '2025-10-09 00:00:00', -369.48, 'Petra Auenheimer', 'VS 10/2025, Meidlinger Hauptstr. 69 Petra Auenheimer'),
(495, '20111', '84722039000', '2025-10-13 00:00:00', 700.00, 'Jerica Steklasa', 'Miete - Oktober 2025 (J. Steklasa, Jerica Steklasa'),
(496, '20111', '84722039000', '2025-10-28 00:00:00', 20.70, 'Brigitte Greiner', 'Nachzahlung Betriebskosten Brigitte Greiner'),
(497, '20111', '84722039000', '2025-10-31 00:00:00', -7.10, 'Österreichische Gesundheitskasse', 'Beitr.KtoNr.: 065015757 Oesterreichische Gesundheitskasse'),
(498, '20111', '84722039000', '2025-10-31 00:00:00', -120.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(499, '20111', '84722039000', '2025-10-31 00:00:00', -200.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(500, '20111', '84722039000', '2025-10-31 00:00:00', 898.62, 'Katharina Reicher', 'Miete Oktober 25 Katharina Reicher'),
(501, '01234', 'AT792011122612019300', '2025-11-05 11:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs'),
(502, '01234', 'AT472011184580265400', '2025-11-04 11:00:00', 83.98, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Nov 2025)'),
(503, '01234', 'AT472011184580265400', '2025-11-04 11:00:00', 1068.91, 'Anna Bondar', 'Mietvertrag, Nov 2025, Bahngasse 14 /Top 2'),
(504, '01234', 'AT863200052909318320', '2025-11-04 11:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Le', '022520047003'),
(505, '01234', 'AT313288000007005994', '2025-11-04 11:00:00', 41.99, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2'),
(506, '01234', 'AT313288000007005994', '2025-11-04 11:00:00', 1068.52, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3'),
(507, '01234', 'AT343438000006222343', '2025-11-03 11:00:00', 850.11, 'Steinkogler  Petra', 'Miete Top4 Steinkogler'),
(508, '20111', '84722039000', '2025-11-03 00:00:00', 850.11, 'Steinkogler  Petra', 'Miete Top4 Steinkogler Steinkogler  Petra'),
(509, '20111', '84722039000', '2025-11-04 00:00:00', -326.16, 'WEG 3423 St. Andrae-Woerdern, Lehne', '022520047003 WEG 3423 St. Andrae-Woerdern, Lehne'),
(510, '20111', '84722039000', '2025-11-04 00:00:00', 41.99, 'Greiner  Brigitte', 'Kfz-Stellplatz Nr. 2 Greiner  Brigitte'),
(511, '20111', '84722039000', '2025-11-04 00:00:00', 83.98, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 Anna Bondar'),
(512, '20111', '84722039000', '2025-11-04 00:00:00', 1068.52, 'Greiner  Brigitte', 'Miete Bahngasse 14/Top 3 Greiner  Brigitte'),
(513, '20111', '84722039000', '2025-11-04 00:00:00', 1068.91, 'Anna Bondar', 'Mietvertrag, Nov 2025, Bahngasse 14 Anna Bondar'),
(514, '20111', '84722039000', '2025-11-05 00:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs Frieda Fuchs'),
(515, '20111', '84722039000', '2025-11-06 00:00:00', -369.48, 'AK HV HI 1120, Meidl.Hptstr.69', 'Vorschreibung 11.2025 1269 /001-5 AK HV HI 1120, Meidl.Hptstr.69'),
(516, '20111', '84722039000', '2025-11-06 00:00:00', 705.85, 'Jerica Steklasa', 'UNTER VORBEHALT! Miete - November 2 Jerica Steklasa'),
(517, '20111', '84722039000', '2025-11-10 00:00:00', -5000.00, 'Thomas Fuchs', 'Privat Thomas Fuchs'),
(518, '20111', '84722039000', '2025-11-13 00:00:00', 22.31, 'Marktgemeinde St. Andrä-Wördern', 'Bankeinzug Nachtr-glicher Einzug Marktgemeinde St. Andrae-Woerdern'),
(519, '20111', '84722039000', '2025-11-15 00:00:00', -648.49, 'FA Tulln', '223849191 FA Tulln'),
(520, '20111', '84722039000', '2025-11-17 00:00:00', -1170.73, 'Marktgemeinde St. Andrä-Wördern', 'Re.Nr. 0 8373 1, Kd.Nr. 10219, Bank Marktgemeinde St. Andrae-Woerdern'),
(521, '20111', '84722039000', '2025-11-18 00:00:00', -1.34, 'AMAZON PAYMENTS EUROPE S.C.A.', '302-3588309-3716369 AMZN Mktp DE 37 AMAZON PAYMENTS EUROPE S.C.A.'),
(522, '20111', '84722039000', '2025-11-18 00:00:00', -39.23, 'AMAZON PAYMENTS EUROPE S.C.A.', '302-3588309-3716369 AMZN Mktp DE 5L AMAZON PAYMENTS EUROPE S.C.A.'),
(523, '20111', '84722039000', '2025-11-18 00:00:00', -50.13, 'AMAZON PAYMENTS EUROPE S.C.A.', '302-3588309-3716369 AMZN Mktp DE 4Q AMAZON PAYMENTS EUROPE S.C.A.'),
(524, '20111', '84722039000', '2025-11-24 00:00:00', -480.00, 'INTER-TREUHAND PRACHNER', '232745 261867 INTER-TREUHAND PRACHNER'),
(525, '20111', '84722039000', '2025-11-28 00:00:00', -14.19, 'Österreichische Gesundheitskasse', 'Beitr.KtoNr.: 065015757 Oesterreichische Gesundheitskasse'),
(526, '20111', '84722039000', '2025-11-28 00:00:00', -240.00, 'Frieda Fuchs', 'Gehalt Frieda Fuchs'),
(527, '20111', '84722039000', '2025-11-28 00:00:00', -400.00, 'Eric Girokonto', 'Gehalt Eric Girokonto'),
(528, '20111', '84722039000', '2025-11-28 00:00:00', 898.62, 'Katharina Reicher', 'Miete November 25 Katharina Reicher'),
(529, '01234', 'AT343438000006222343', '2025-12-03 11:00:00', 850.11, 'Steinkogler  Petra', 'Miete Top4 Steinkogler'),
(530, '01234', 'AT792011122612019300', '2025-12-03 11:00:00', 169.20, 'Frieda Fuchs', 'BK Top1 Frieda Fuchs'),
(531, '01234', 'AT322011122611252100', '2025-12-02 11:00:00', -4927.20, 'Thomas Fuchs', 'Ueberweisung Thomas Fuchs'),
(532, '01234', 'AT572011128042894302', '2025-12-02 11:00:00', 4927.20, 'Martina Fuchs', 'Eigenuebertrag'),
(533, '01234', 'AT362011129711349000', '2025-12-02 11:00:00', 705.85, 'Jerica Steklasa', 'UNTER VORBEHALT! Miete - Dezember 2 025 (J. Steklasa, M. Chikwereuba), Meidlinger Hauptstrasse 69/1/5, 112 0 Wien'),
(534, '01234', 'AT472011184580265400', '2025-12-01 11:00:00', 83.98, 'Anna Bondar', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Dec 2025)'),
(535, '01234', 'AT472011184580265400', '2025-12-01 11:00:00', 1068.91, 'Anna Bondar', 'Mietvertrag, Dec 2025, Bahngasse 14 /Top 2');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `bank_imports`
--

CREATE TABLE `bank_imports` (
  `id` int(11) NOT NULL,
  `trans_hash` varchar(191) NOT NULL,
  `valuta` date NOT NULL,
  `amount` decimal(15,2) NOT NULL,
  `sender` varchar(255) NOT NULL,
  `iban` varchar(40) DEFAULT NULL,
  `text` text DEFAULT NULL,
  `status` enum('neu','verbucht','ignoriert') NOT NULL DEFAULT 'neu'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `bank_imports`
--

INSERT INTO `bank_imports` (`id`, `trans_hash`, `valuta`, `amount`, `sender`, `iban`, `text`, `status`) VALUES
(52, '201002601302AEI-T0BKYCCPHCGI', '2026-01-30', 898.62, 'Katharina Reicher', 'AT501200010013537708', 'Miete Jänner 2026', 'neu'),
(53, '201112601302CDC-002J93X3896Y', '2026-01-30', -120.00, 'Frieda Fuchs', 'AT792011122612019300', 'Gehalt', 'neu'),
(54, '201112601302CDC-002IWEACRTPJ', '2026-01-30', -7.10, 'Österreichische Gesundheitskasse', 'AT576000000002200152', 'Beitr.KtoNr.: 065015757', 'neu'),
(55, '201112601302CDC-002FNNSOAPP3', '2026-01-30', -200.00, 'Eric Fuchs', 'AT162011183946922500', 'Gehalt', 'neu'),
(56, '600002601222AEI-F4642KMVSCN6', '2026-01-27', -535.53, 'EVN Vertrieb GmbH  Co KG', 'AT246000000510341163', '3007903064 St. Andrae-Woerdern, Bah ngasse 14 ABR 716080034379 115,29 A BR 716080034380 152,81 ABR 71608003 4381 267,43', 'verbucht'),
(57, '201112601172AAU-0054VK4U08Y2', '2026-01-19', 0.00, 'Unbekannt', '', 'Guthaben auf Girokonten und Spareinlagen sind gemäß Einlagensicherungs- und Anlegerentschädigungsgesetz erstattungsfähig. Nähere Informationen dazu entnehmen Sie bitte dem \'Informationsbogen für den Einleger\' - abholbereit in jeder Filiale bzw. abrufbar unter: www.erstebank.at/einlagensicherung und www.sparkasse.at/einlagensicherung.', 'neu'),
(58, '201112601152AIP-00M3LF32U37U', '2026-01-16', -32.86, 'WEG 3423 St. Andrae-Woerdern, Lehne', 'AT863200052909318320', '', 'neu'),
(59, '201112601082CDC-006X7TOOZYXX', '2026-01-08', -6000.00, 'Thomas Fuchs', 'AT322011122611252100', 'Privatentnahme', 'neu'),
(60, '201002601072AEI-12PC9F026817', '2026-01-08', -372.31, 'AK HV HI 1120, Meidl.Hptstr.69', 'AT153200006912471140', 'Vorschreibung 01.2026 1269 /001-5', 'neu'),
(61, '201002601062AEI-56P2WQ017943', '2026-01-07', 41.99, 'Greiner  Brigitte', 'AT313288000007005994', 'Kfz-Stellplatz Nr. 2', 'verbucht'),
(62, '201002601062AEI-57P2WT020546', '2026-01-07', 1068.52, 'Greiner  Brigitte', 'AT313288000007005994', 'Miete Bahngasse 14/Top 3', 'neu'),
(63, '201002601052AEI-54PB99050090', '2026-01-05', 850.11, 'Steinkogler  Petra', 'AT343438000006222343', '', 'neu'),
(64, '201112601052AB3-DD1001029141', '2026-01-05', 169.20, 'Frieda Fuchs', 'AT792011122612019300', 'BK Top1 Frieda Fuchs', 'verbucht'),
(65, '201112601042AIP-00CZQAJ07IVP', '2026-01-05', 686.68, 'Jerica Steklasa', 'AT362011129711349000', 'UNTER VORBEHALT! Miete - Januar 202 6 (J. Steklasa, M. Chikwereuba), Me idlinger Hauptstrasse 69/1/5, 1120 Wien', 'neu'),
(66, '201112601032AIP-00B02J751KVU', '2026-01-05', 83.98, 'Anna Bondar', 'AT472011184580265400', 'Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Jan 2026)', 'neu'),
(67, '201112601032AIP-00AZR3DGKV0Q', '2026-01-05', 1068.91, 'Anna Bondar', 'AT472011184580265400', 'Mietvertrag, Jan 2026, Bahngasse 14 /Top 2', 'neu'),
(68, '201112601022AB3-DD1001219745', '2026-01-02', -326.16, 'NV Immobilien GmbH', 'AT863200052909318320', '', 'neu');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `buchungen`
--

CREATE TABLE `buchungen` (
  `id` int(11) NOT NULL,
  `rechnungtext` varchar(255) NOT NULL,
  `bruttobetrag` decimal(10,2) NOT NULL,
  `nettobetrag` decimal(10,2) NOT NULL,
  `ustbetrag` decimal(10,2) DEFAULT NULL,
  `ust` enum('0','10','13','20') NOT NULL,
  `bk` enum('bk','nonbk','heizung','miete','wasser','strom') NOT NULL,
  `ausgabe` tinyint(1) NOT NULL DEFAULT 0,
  `datum` date NOT NULL,
  `sachkonto_id` int(10) DEFAULT NULL,
  `einheit_id` int(11) DEFAULT NULL,
  `liegenschaft_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `buchungen`
--

INSERT INTO `buchungen` (`id`, `rechnungtext`, `bruttobetrag`, `nettobetrag`, `ustbetrag`, `ust`, `bk`, `ausgabe`, `datum`, `sachkonto_id`, `einheit_id`, `liegenschaft_id`) VALUES
(1, 'Wassergebühr 2. Qu. 2024, Bereitstellungsgebühr (anteilig nur Monat Juni)\r\n', 10.45, 9.50, 0.95, '10', 'wasser', 1, '2024-04-22', 26, NULL, 1),
(2, 'Wassergebühr 3. Qu. 2024, Bereitstellungsgebühr', 31.35, 28.50, 2.85, '10', 'wasser', 1, '2024-07-23', 26, NULL, 1),
(3, 'Wassergebühr 4. Qu. 2024, Bereitstellungsgebühr, Wasserbezugsgebühr Akonto', 52.25, 47.50, 4.75, '10', 'wasser', 1, '2024-10-26', 26, NULL, 1),
(4, 'Abrg. Wasserbezugsgebühr, 23.06.-01.07.2024', 84.55, 76.86, 7.69, '10', 'wasser', 1, '2024-10-26', 26, NULL, 1),
(7, 'Grundsteuer 2. Qu. 2024 (anteilig nur Monat Juni)', 26.80, 26.80, NULL, '0', 'bk', 1, '2024-04-22', 26, NULL, 1),
(8, 'Grundsteuer 3. Qu. 2024', 80.40, 80.40, NULL, '0', 'bk', 1, '2024-07-23', 26, NULL, 1),
(9, 'Grundsteuer 4. Qu. 2024', 80.40, 80.40, NULL, '0', 'bk', 1, '2024-10-26', 26, NULL, 1),
(10, 'Abwassergebühr 2. Qu. 2024 (anteilig nur Monat Juni)', 86.99, 79.08, 7.91, '10', 'bk', 1, '2024-04-22', 26, NULL, 1),
(11, 'Abwassergebühr 3. Qu. 2024', 260.96, 237.24, 23.72, '10', 'bk', 1, '2024-07-23', 26, NULL, 1),
(12, 'Abwassergebühr 4. Qu. 2024', 247.94, 225.40, 22.54, '10', 'bk', 1, '2024-10-26', 26, NULL, 1),
(13, 'Aufrollung laut Bescheid', -13.02, -11.84, -1.18, '10', 'bk', 1, '2024-10-25', 26, NULL, 1),
(14, 'Müllgebühr 2. Qu. 2024 (anteilig nur Monat Juni)', 25.66, 23.33, 2.33, '10', 'bk', 1, '2024-04-22', 26, NULL, 1),
(15, 'Gebührenbremse 01.01.-31.12.2024', -34.78, -31.62, -3.16, '10', 'bk', 1, '2024-04-22', 26, NULL, 1),
(16, 'Müllgebühr 3. Qu. 2024', 197.71, 179.74, 17.97, '10', 'bk', 1, '2024-07-23', 26, NULL, 1),
(17, 'Müllgebühr 4. Qu. 2024', 166.78, 151.62, 15.16, '10', 'bk', 1, '2024-10-26', 26, NULL, 1),
(18, 'NÖ Seuchenvors. 2. Qu. 2024 (anteilig nur Monat Juni)', 1.25, 1.25, NULL, '0', 'bk', 1, '2024-04-22', 26, NULL, 1),
(19, 'NÖ Seuchenvors. 3. Qu. 2024', 8.19, 8.19, NULL, '0', 'bk', 1, '2024-07-23', 26, NULL, 1),
(20, 'NÖ Seuchenvors. 4. Qu. 2024', 7.05, 7.05, NULL, '0', 'bk', 1, '2024-10-26', 26, NULL, 1),
(21, 'Jahresprämie 2024 (anteilig 7 Monate)', 1650.83, 1650.83, NULL, '0', 'bk', 1, '2024-04-02', 26, NULL, 1),
(22, 'Entgelt 06-12/2024 à € 120,00', 840.00, 840.00, NULL, '0', 'bk', 1, '2024-06-01', 26, NULL, 1),
(23, 'Sonderzahlung UZ 06/2024', 80.00, 80.00, NULL, '0', 'bk', 1, '2024-06-19', 26, NULL, 1),
(24, 'Sonderzahlung WR 11/2024', 80.00, 80.00, NULL, '0', 'bk', 1, '2024-11-21', 26, NULL, 1),
(25, 'Mitarbeitervorsorgekasse 7,8,9,10,12/2024 à € 1,84', 9.20, 9.20, NULL, '0', 'bk', 1, '2024-06-01', 26, NULL, 1),
(26, 'Mitarbeitervorsorgekasse 6/2024 (Lohn inkl. UZ)', 3.06, 3.06, NULL, '0', 'bk', 1, '2024-06-19', 26, NULL, 1),
(27, 'Mitarbeitervorsorgekasse 11/2024 (Lohn inkl. WR)', 3.06, 3.06, NULL, '0', 'bk', 1, '2024-11-21', 26, NULL, 1),
(28, 'Straßenbesen, Rasendünger', 43.48, 36.23, 7.25, '20', 'bk', 1, '2024-07-01', 26, NULL, 1),
(29, 'VILEDA Boden-Wischbezug', 15.29, 12.74, 2.55, '20', 'bk', 1, '2024-10-04', 26, NULL, 1),
(30, 'Schneeschaufel, Auftausiedesalz, Unkrautstecher, Kehrschaufel, Fugensand', 130.52, 108.77, 21.75, '20', 'bk', 1, '2024-10-12', 26, NULL, 1),
(31, 'Besen und Grubber 3 Zinken', 39.48, 32.90, 6.58, '20', 'bk', 1, '2024-10-24', 26, NULL, 1),
(32, 'Solidarbeitrag Nutzung Gemeinschaftsraum (Strom/Wasser/Abwasser)', -12.00, -10.00, -2.00, '20', 'bk', 1, '2024-12-26', 26, NULL, 1),
(33, 'EVN (Tarif Optima Garant 49,49 Cent/kWh)	Rg. 29.01.-09.10.2024 (anteilig 131 Tage)\r\n', 1371.94, 1143.28, 228.66, '20', 'strom', 1, '2024-10-12', 26, NULL, 1),
(35, 'EVN (Tarif Optima Aktiv 13,12 Cent/kWh)	Rg. 10.10.-31.10.2024\r\n', 54.14, 45.12, 9.02, '20', 'strom', 1, '2024-11-06', 26, NULL, 1),
(36, 'EVN (Tarif Optima Aktiv  14,02 Cent/kWh)	Rg. 01.11.-30.11.2024\r\n', 122.56, 102.13, 20.43, '20', 'strom', 1, '2024-12-04', 26, NULL, 1),
(59, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2024-06-03', 24, 5, 1),
(60, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2024-06-03', 23, 5, 1),
(61, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2024-12-03', 24, 5, 1),
(62, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2024-12-03', 23, 5, 1),
(63, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2024-12-03', 20, 5, 1),
(64, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2024-11-04', 24, 5, 1),
(65, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2024-11-04', 23, 5, 1),
(66, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2024-11-04', 20, 5, 1),
(67, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2024-10-03', 24, 5, 1),
(68, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2024-10-03', 23, 5, 1),
(69, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2024-10-03', 20, 5, 1),
(70, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2024-09-03', 24, 5, 1),
(71, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2024-09-03', 23, 5, 1),
(72, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2024-09-03', 20, 5, 1),
(73, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2024-08-05', 24, 5, 1),
(74, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2024-08-05', 23, 5, 1),
(75, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2024-08-05', 20, 5, 1),
(76, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2025-01-03', 24, 5, 1),
(77, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-01-03', 23, 5, 1),
(78, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2025-01-03', 20, 5, 1),
(79, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2024-07-03', 24, 5, 1),
(80, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2024-07-03', 23, 5, 1),
(81, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2024-07-03', 20, 5, 1),
(84, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2025-02-03', 24, 5, 1),
(85, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-02-03', 23, 5, 1),
(86, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2025-02-03', 20, 5, 1),
(87, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2025-03-03', 24, 5, 1),
(88, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-03-03', 23, 5, 1),
(89, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2025-03-03', 20, 5, 1),
(90, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2025-04-03', 24, 5, 1),
(91, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-04-03', 23, 5, 1),
(92, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2025-04-03', 20, 5, 1),
(93, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2025-05-05', 24, 5, 1),
(94, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-05-05', 23, 5, 1),
(95, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2025-05-05', 20, 5, 1),
(96, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2025-06-03', 24, 5, 1),
(97, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-06-03', 23, 5, 1),
(98, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2025-06-03', 20, 5, 1),
(99, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2024-12-05', 24, 2, 1),
(100, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2024-12-05', 23, 2, 1),
(101, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2024-11-05', 24, 2, 1),
(102, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2024-11-05', 23, 2, 1),
(103, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2024-10-07', 24, 2, 1),
(104, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2024-10-07', 23, 2, 1),
(105, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2024-09-05', 24, 2, 1),
(106, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2024-09-05', 23, 2, 1),
(107, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2024-08-05', 24, 2, 1),
(108, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2024-08-05', 23, 2, 1),
(109, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2024-07-05', 24, 2, 1),
(110, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2024-07-05', 23, 2, 1),
(111, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-01-07', 24, 2, 1),
(112, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-01-07', 23, 2, 1),
(113, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2024-06-05', 24, 2, 1),
(114, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2024-06-05', 23, 2, 1),
(115, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-02-05', 24, 2, 1),
(116, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-02-05', 23, 2, 1),
(117, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-03-05', 24, 2, 1),
(118, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-03-05', 23, 2, 1),
(119, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-04-07', 24, 2, 1),
(120, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-04-07', 23, 2, 1),
(121, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-05-05', 24, 2, 1),
(122, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-05-05', 23, 2, 1),
(123, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-06-05', 24, 2, 1),
(124, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-06-05', 23, 2, 1),
(125, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2024-12-02', 24, 3, 1),
(126, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2024-12-02', 23, 3, 1),
(127, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2024-12-02', 20, 3, 1),
(128, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-12-02', 27, 10, 1),
(129, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-12-02', 27, 11, 1),
(130, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2025-01-02', 24, 3, 1),
(131, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-01-02', 23, 3, 1),
(132, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2025-01-02', 20, 3, 1),
(133, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-01-02', 27, 10, 1),
(134, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-01-02', 27, 11, 1),
(135, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2024-11-04', 24, 3, 1),
(136, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2024-11-04', 23, 3, 1),
(137, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2024-11-04', 20, 3, 1),
(138, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-11-04', 27, 10, 1),
(139, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-11-04', 27, 11, 1),
(140, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2024-10-02', 24, 3, 1),
(141, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2024-10-02', 23, 3, 1),
(142, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2024-10-02', 20, 3, 1),
(143, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-10-02', 27, 10, 1),
(144, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-10-02', 27, 11, 1),
(145, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2024-09-03', 24, 3, 1),
(146, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2024-09-03', 23, 3, 1),
(147, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2024-09-03', 20, 3, 1),
(148, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-09-03', 27, 10, 1),
(149, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-09-03', 27, 11, 1),
(150, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2024-08-05', 24, 3, 1),
(151, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2024-08-05', 23, 3, 1),
(152, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2024-08-05', 20, 3, 1),
(153, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-08-05', 27, 10, 1),
(154, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-08-05', 27, 11, 1),
(155, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2024-07-03', 24, 3, 1),
(156, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2024-07-03', 23, 3, 1),
(157, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2024-07-03', 20, 3, 1),
(158, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-07-03', 27, 10, 1),
(159, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-07-03', 27, 11, 1),
(160, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2024-06-04', 24, 3, 1),
(161, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2024-06-04', 23, 3, 1),
(162, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-06-04', 27, 10, 1),
(163, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-06-04', 27, 11, 1),
(164, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2025-02-03', 24, 3, 1),
(165, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-02-03', 23, 3, 1),
(166, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2025-02-03', 20, 3, 1),
(167, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-02-03', 27, 10, 1),
(168, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-02-03', 27, 11, 1),
(169, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2025-03-03', 24, 3, 1),
(170, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-03-03', 23, 3, 1),
(171, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2025-03-03', 20, 3, 1),
(172, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-03-03', 27, 10, 1),
(173, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-03-03', 27, 11, 1),
(174, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2025-03-31', 24, 3, 1),
(175, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-03-31', 23, 3, 1),
(176, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2025-03-31', 20, 3, 1),
(177, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-03-31', 27, 10, 1),
(178, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-03-31', 27, 11, 1),
(179, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2025-05-02', 24, 3, 1),
(180, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-05-02', 23, 3, 1),
(181, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2025-05-02', 20, 3, 1),
(182, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-05-02', 27, 10, 1),
(183, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-05-02', 27, 11, 1),
(184, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2025-06-02', 24, 3, 1),
(185, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-06-02', 23, 3, 1),
(186, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2025-06-02', 20, 3, 1),
(187, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-06-02', 27, 10, 1),
(188, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-06-02', 27, 11, 1),
(189, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2024-12-04', 24, 4, 1),
(190, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2024-12-04', 23, 4, 1),
(191, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2024-12-04', 20, 4, 1),
(192, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-12-04', 27, 7, 1),
(193, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2024-11-05', 24, 4, 1),
(194, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2024-11-05', 23, 4, 1),
(195, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2024-11-05', 20, 4, 1),
(196, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-11-05', 27, 7, 1),
(197, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2024-10-04', 24, 4, 1),
(198, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2024-10-04', 23, 4, 1),
(199, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2024-10-04', 20, 4, 1),
(200, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-10-04', 27, 7, 1),
(201, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2024-09-04', 24, 4, 1),
(202, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2024-09-04', 23, 4, 1),
(203, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2024-09-04', 20, 4, 1),
(204, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-09-04', 27, 7, 1),
(205, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2024-08-06', 24, 4, 1),
(206, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2024-08-06', 23, 4, 1),
(207, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2024-08-06', 20, 4, 1),
(208, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-08-06', 27, 7, 1),
(209, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2024-06-03', 24, 4, 1),
(210, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2024-06-03', 23, 4, 1),
(211, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2024-07-02', 20, 4, 1),
(212, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2024-07-02', 27, 7, 1),
(213, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-01-07', 24, 4, 1),
(214, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-01-07', 23, 4, 1),
(215, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2025-01-07', 20, 4, 1),
(216, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-01-07', 27, 7, 1),
(217, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-02-04', 24, 4, 1),
(218, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-02-04', 23, 4, 1),
(219, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2025-02-04', 20, 4, 1),
(220, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-02-04', 27, 7, 1),
(221, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-03-04', 24, 4, 1),
(222, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-03-04', 23, 4, 1),
(223, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2025-03-04', 20, 4, 1),
(224, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-03-04', 27, 7, 1),
(225, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-04-04', 24, 4, 1),
(226, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-04-04', 23, 4, 1),
(227, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2025-04-04', 20, 4, 1),
(228, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-04-04', 27, 7, 1),
(229, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-05-06', 24, 4, 1),
(230, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-05-06', 23, 4, 1),
(231, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2025-05-06', 20, 4, 1),
(232, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-05-06', 27, 7, 1),
(233, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-06-04', 24, 4, 1),
(234, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-06-04', 23, 4, 1),
(235, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2025-06-04', 20, 4, 1),
(236, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-06-04', 27, 7, 1),
(237, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2024-12-02', 22, 1, 2),
(238, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2024-12-02', 21, 1, 2),
(239, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-01-02', 22, 1, 2),
(240, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2025-01-02', 21, 1, 2),
(241, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2024-10-30', 22, 1, 2),
(242, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2024-10-30', 21, 1, 2),
(243, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2024-10-02', 22, 1, 2),
(244, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2024-10-02', 21, 1, 2),
(245, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2024-09-03', 22, 1, 2),
(246, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2024-09-03', 21, 1, 2),
(247, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-02-05', 22, 1, 2),
(248, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2025-02-05', 21, 1, 2),
(249, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-02-27', 22, 1, 2),
(250, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2025-02-27', 21, 1, 2),
(251, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-04-02', 22, 1, 2),
(252, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2025-04-02', 21, 1, 2),
(253, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-05-05', 22, 1, 2),
(254, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2025-05-05', 21, 1, 2),
(255, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-05-30', 22, 1, 2),
(256, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2025-05-30', 21, 1, 2),
(257, 'EVN', 167.42, 139.52, 27.90, '20', 'strom', 1, '2025-01-23', 26, NULL, 1),
(258, 'EVN', 228.75, 190.63, 38.12, '20', 'strom', 1, '2025-02-28', 26, NULL, 1),
(259, 'EVN', 176.95, 147.46, 29.49, '20', 'strom', 1, '2025-03-20', 26, NULL, 1),
(260, 'EVN', 151.32, 126.10, 25.22, '20', 'strom', 1, '2025-04-22', 26, NULL, 1),
(261, 'EVN', 70.82, 59.02, 11.80, '20', 'strom', 1, '2025-05-22', 26, NULL, 1),
(262, 'EVN', 53.36, 44.47, 8.89, '20', 'strom', 1, '2025-06-24', 26, NULL, 1),
(263, 'BK LEH265 Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-07-01', 22, 1, 2),
(264, 'Miete LEH265 Reicher', 641.50, 583.18, 58.32, '10', 'miete', 0, '2025-07-01', 21, 1, 2),
(265, 'BK Top4 Steinkogler', 154.29, 140.26, 14.03, '10', 'bk', 0, '2025-07-03', 24, 5, 1),
(266, 'BK Heizung Top4 Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-07-03', 23, 5, 1),
(267, 'Miete Top4 Steinkogler', 649.96, 590.87, 59.09, '10', 'miete', 0, '2025-07-03', 20, 5, 1),
(268, 'BK Top2 Bondar', 193.99, 176.35, 17.64, '10', 'bk', 0, '2025-07-03', 24, 3, 1),
(269, 'BK Heizung Top2 Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-07-03', 23, 3, 1),
(270, 'Miete Top2 Bondar', 817.22, 742.93, 74.29, '10', 'miete', 0, '2025-07-03', 20, 3, 1),
(271, 'Miete SP5 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-07-03', 27, 10, 1),
(272, 'Miete SP6 Top2 Bondar', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-07-03', 27, 11, 1),
(273, 'BK Top3 Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-07-07', 24, 4, 1),
(274, 'BK Heizung Top3 Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-07-07', 23, 4, 1),
(275, 'Miete Top3 Pieringer', 816.91, 742.65, 74.26, '10', 'miete', 0, '2025-07-07', 20, 4, 1),
(276, 'Miete SP2 Top3 Pieringer', 40.80, 34.00, 6.80, '20', 'miete', 0, '2025-07-04', 27, 7, 1),
(277, 'BK Top1 Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-07-07', 24, 2, 1),
(278, 'BK Heizung Top1 Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-07-07', 23, 2, 1),
(279, 'EVN', 44.25, 36.88, 7.38, '20', 'strom', 1, '2025-07-22', 26, NULL, 1),
(280, 'BK Top1 Fuchs Nachzahlung', 15.05, 13.68, 1.37, '10', 'bk', 0, '2025-07-01', 24, 2, 1),
(281, 'BK Heizung Top1 Fuchs Nachzahlung', 11.99, 9.99, 2.00, '20', 'heizung', 0, '2025-07-01', 23, 2, 1),
(282, 'BK Top2 Bondar Nachzahlung', 244.99, 222.72, 22.27, '10', 'bk', 0, '2025-07-07', 24, 3, 1),
(283, 'BK Heizung Top2 Bondar Nachzahlung', -26.68, -22.23, -4.45, '20', 'heizung', 0, '2025-07-07', 23, 3, 1),
(284, 'Miete Top2 Bondar Nachzahlung', 118.85, 108.05, 10.80, '10', 'miete', 0, '2025-07-07', 20, 3, 1),
(285, 'Miete SP5/6 Top2 Bondar Nachzahlung', 11.90, 9.92, 1.98, '20', 'miete', 0, '2025-07-07', 27, 10, 1),
(287, 'BK Top4 Steinkogler Nachzahlung', 52.19, 47.45, 4.74, '10', 'bk', 0, '2025-07-14', 24, 5, 1),
(288, 'BK Heizung Top4 Steinkogler Nachzahlung', -3.17, -2.64, -0.53, '20', 'heizung', 0, '2025-07-14', 23, 5, 1),
(289, 'Miete Top4 Steinkogler Nachzahlung', 94.55, 85.95, 8.60, '10', 'miete', 0, '2025-07-07', 20, 5, 1),
(290, 'Hausbesorger', 240.00, 240.00, 0.00, '0', 'bk', 1, '2025-06-30', 26, NULL, 1),
(291, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-01-31', 26, NULL, 1),
(292, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-02-28', 26, NULL, 1),
(293, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-03-31', 26, NULL, 1),
(294, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-04-30', 26, NULL, 1),
(295, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-05-30', 26, NULL, 1),
(296, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-01-31', 26, NULL, 1),
(297, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-02-28', 26, NULL, 1),
(298, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-03-31', 26, NULL, 1),
(299, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-04-30', 26, NULL, 1),
(300, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-05-30', 26, NULL, 1),
(301, 'Sozialversicherungsbeiträge', 14.19, 14.19, 0.00, '0', 'bk', 1, '2025-06-30', 26, NULL, 1),
(356, 'Helvetia Versicherung', 2894.94, 2894.94, 0.00, '0', 'bk', 1, '2025-04-01', 26, NULL, 1),
(399, 'Außenanlage', 41.46, 34.55, 6.91, '20', 'bk', 1, '2025-04-11', 26, NULL, 1),
(400, 'Gartenutensilien', 12.99, 10.83, 2.17, '20', 'bk', 1, '2025-04-04', 26, NULL, 1),
(401, 'Grundsteuer B', 80.40, 0.00, 0.00, '0', 'bk', 1, '2025-05-12', 26, NULL, 1),
(402, 'Wasserbezugsgebühr', 20.90, 19.00, 1.90, '10', 'wasser', 1, '2025-05-12', 26, NULL, 1),
(403, 'WasserBereitstellungsgebühr', 31.35, 28.50, 2.85, '10', 'wasser', 1, '2025-05-12', 26, NULL, 1),
(404, 'Kanalbenutzungsgebühr', 271.99, 247.27, 24.73, '10', 'bk', 1, '2025-05-12', 26, NULL, 1),
(406, 'Abfallwirtschaftsabgabe', 28.76, 26.12, 2.61, '10', 'bk', 1, '2025-05-12', 26, NULL, 1),
(407, 'NÖ Seuchenvorsorgeabgabe', 7.05, 7.05, 0.00, '0', 'bk', 1, '2025-05-12', 26, NULL, 1),
(408, 'Müllsäcke', 18.00, 15.00, 3.00, '20', 'bk', 1, '2025-05-12', 26, NULL, 1),
(409, 'Garderobenhaken', 10.00, 8.33, 1.67, '20', 'bk', 1, '2025-07-16', 26, NULL, 1),
(418, 'Gardena Schlauchbox', 178.19, 148.49, 29.70, '20', 'bk', 1, '2025-07-21', 26, NULL, 1),
(419, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-07-31', 26, NULL, 1),
(420, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-08-29', 26, NULL, 1),
(475, 'BHG14_4_Steinkogler - HMZ Petra Steinkogler', 668.87, 608.06, 60.81, '10', 'miete', 0, '2025-08-04', 20, 5, 1),
(476, 'BHG14_4_Steinkogler - BK Petra Steinkogler', 154.26, 140.24, 14.02, '10', 'bk', 0, '2025-08-04', 24, 5, 1),
(477, 'BHG14_4_Steinkogler - Heizung Petra Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-08-04', 23, 5, 1),
(478, 'LEH265_Reicher - HMZ Katharina Reicher', 660.12, 600.11, 60.01, '10', 'miete', 0, '2025-08-01', 21, 1, 2),
(479, 'LEH265_Reicher - BK Katharina Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-08-01', 22, 1, 2),
(480, 'BHG14_SP2_Pieringer - HMZ Tamara Pieringer', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-08-01', 27, 7, 1),
(481, 'BHG14_3_Pieringer - HMZ Tamara Pieringer', 840.69, 764.26, 76.43, '10', 'miete', 0, '2025-08-04', 20, 4, 1),
(482, 'BHG14_3_Pieringer - BK Tamara Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-08-04', 24, 4, 1),
(483, 'BHG14_3_Pieringer - Heizung Tamara Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-08-04', 23, 4, 1),
(485, 'BHG14_1_Fuchs - BK Frieda Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-08-05', 24, 2, 1),
(486, 'BHG14_1_Fuchs - Heizung Frieda Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-08-05', 23, 2, 1),
(487, 'BHG14_2_Bondar - HMZ Anna Bondar', 840.99, 764.54, 76.45, '10', 'miete', 0, '2025-08-04', 20, 3, 1),
(488, 'BHG14_2_Bondar - BK Anna Bondar', 194.00, 176.36, 17.64, '10', 'bk', 0, '2025-08-04', 24, 3, 1),
(489, 'BHG14_2_Bondar - Heizung Anna Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-08-04', 23, 3, 1),
(490, 'BHG_SP5_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-08-01', 27, 10, 1),
(491, 'BHG_SP6_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-08-01', 27, 11, 1),
(492, 'BHG14_4_Steinkogler - HMZ Petra Steinkogler', 668.87, 608.06, 60.81, '10', 'miete', 0, '2025-09-03', 20, 5, 1),
(493, 'BHG14_4_Steinkogler - BK Petra Steinkogler', 154.26, 140.24, 14.02, '10', 'bk', 0, '2025-09-03', 24, 5, 1),
(494, 'BHG14_4_Steinkogler - Heizung Petra Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-09-03', 23, 5, 1),
(495, 'LEH265_Reicher - HMZ Katharina Reicher', 660.12, 600.11, 60.01, '10', 'miete', 0, '2025-09-02', 21, 1, 2),
(496, 'LEH265_Reicher - BK Katharina Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-09-02', 22, 1, 2),
(497, 'BHG14_SP2_Pieringer - HMZ Tamara Pieringer', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-09-01', 27, 7, 1),
(498, 'BHG14_3_Pieringer - HMZ Tamara Pieringer', 840.69, 764.26, 76.43, '10', 'miete', 0, '2025-09-04', 20, 4, 1),
(499, 'BHG14_3_Pieringer - BK Tamara Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-09-04', 24, 4, 1),
(500, 'BHG14_3_Pieringer - Heizung Tamara Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-09-04', 23, 4, 1),
(501, 'BHG14_2_Bondar - HMZ Anna Bondar', 840.99, 764.54, 76.45, '10', 'miete', 0, '2025-09-01', 20, 3, 1),
(502, 'BHG14_2_Bondar - BK Anna Bondar', 194.00, 176.36, 17.64, '10', 'bk', 0, '2025-09-01', 24, 3, 1),
(503, 'BHG14_2_Bondar - Heizung Anna Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-09-01', 23, 3, 1),
(504, 'BHG_SP6_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-09-01', 27, 11, 1),
(505, 'BHG_SP5_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-09-01', 27, 10, 1),
(506, 'BHG14_4_Steinkogler - HMZ Petra Steinkogler', 668.87, 608.06, 60.81, '10', 'miete', 0, '2025-10-01', 20, 5, 1),
(507, 'BHG14_4_Steinkogler - BK Petra Steinkogler', 154.26, 140.24, 14.02, '10', 'bk', 0, '2025-10-01', 24, 5, 1),
(508, 'BHG14_4_Steinkogler - Heizung Petra Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-10-01', 23, 5, 1),
(509, 'LEH26_5_Reicher - HMZ Katharina Reicher', 660.12, 600.11, 60.01, '10', 'miete', 0, '2025-10-01', 21, 1, 2),
(510, 'LEH26_5_Reicher - BK Katharina Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-10-01', 22, 1, 2),
(511, 'BHG14_SP2_Pieringer - HMZ Tamara Pieringer', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-10-01', 27, 7, 1),
(512, 'BHG14_3_Pieringer - HMZ Tamara Pieringer', 840.69, 764.26, 76.43, '10', 'miete', 0, '2025-10-01', 20, 4, 1),
(513, 'BHG14_3_Pieringer - BK Tamara Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-10-01', 24, 4, 1),
(514, 'BHG14_3_Pieringer - Heizung Tamara Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-10-01', 23, 4, 1),
(515, 'BHG14_1_Fuchs - BK Frieda Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-10-01', 24, 2, 1),
(516, 'BHG14_1_Fuchs - Heizung Frieda Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-10-01', 23, 2, 1),
(517, 'BHG14_2_Bondar - HMZ Anna Bondar', 840.99, 764.54, 76.45, '10', 'miete', 0, '2025-10-01', 20, 3, 1),
(518, 'BHG14_2_Bondar - BK Anna Bondar', 194.00, 176.36, 17.64, '10', 'bk', 0, '2025-10-01', 24, 3, 1),
(519, 'BHG14_2_Bondar - Heizung Anna Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-10-01', 23, 3, 1),
(520, 'BHG14_SP6_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-10-01', 27, 11, 1),
(521, 'BHG14_SP5_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-10-01', 27, 10, 1),
(522, 'BHG14_4_Steinkogler - HMZ Petra Steinkogler', 668.87, 608.06, 60.81, '10', 'miete', 0, '2025-11-03', 20, 5, 1),
(523, 'BHG14_4_Steinkogler - BK Petra Steinkogler', 154.26, 140.24, 14.02, '10', 'bk', 0, '2025-11-03', 24, 5, 1),
(524, 'BHG14_4_Steinkogler - Heizung Petra Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-11-03', 23, 5, 1),
(525, 'LEH26_5_Reicher - HMZ Katharina Reicher', 660.12, 600.11, 60.01, '10', 'miete', 0, '2025-11-01', 21, 1, 2),
(526, 'LEH26_5_Reicher - BK Katharina Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-11-01', 22, 1, 2),
(527, 'BHG14_SP2_Pieringer - HMZ Tamara Pieringer', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-11-01', 27, 7, 1),
(528, 'BHG14_3_Pieringer - HMZ Tamara Pieringer', 840.69, 764.26, 76.43, '10', 'miete', 0, '2025-11-04', 20, 4, 1),
(529, 'BHG14_3_Pieringer - BK Tamara Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-11-04', 24, 4, 1),
(530, 'BHG14_3_Pieringer - Heizung Tamara Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-11-04', 23, 4, 1),
(531, 'BHG14_1_Fuchs - BK Frieda Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-11-05', 24, 2, 1),
(532, 'BHG14_1_Fuchs - Heizung Frieda Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-11-05', 23, 2, 1),
(533, 'BHG14_SP5_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-11-01', 27, 10, 1),
(534, 'BHG14_2_Bondar - HMZ Anna Bondar', 840.99, 764.54, 76.45, '10', 'miete', 0, '2025-11-04', 20, 3, 1),
(535, 'BHG14_2_Bondar - BK Anna Bondar', 194.00, 176.36, 17.64, '10', 'bk', 0, '2025-11-04', 24, 3, 1),
(536, 'BHG14_2_Bondar - Heizung Anna Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-11-04', 23, 3, 1),
(537, 'BHG14_SP6_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-11-01', 27, 11, 1),
(538, 'BHG14_4_Steinkogler - HMZ Petra Steinkogler', 668.87, 608.06, 60.81, '10', 'miete', 0, '2025-12-03', 20, 5, 1),
(539, 'BHG14_4_Steinkogler - BK Petra Steinkogler', 154.26, 140.24, 14.02, '10', 'bk', 0, '2025-12-03', 24, 5, 1),
(540, 'BHG14_4_Steinkogler - Heizung Petra Steinkogler', 26.98, 22.48, 4.50, '20', 'heizung', 0, '2025-12-03', 23, 5, 1),
(541, 'LEH26_5_Reicher - HMZ Katharina Reicher', 660.12, 600.11, 60.01, '10', 'miete', 0, '2025-12-01', 21, 1, 2),
(542, 'LEH26_5_Reicher - BK Katharina Reicher', 238.50, 216.82, 21.68, '10', 'bk', 0, '2025-12-01', 22, 1, 2),
(543, 'BHG14_SP2_Pieringer - HMZ Tamara Pieringer', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-12-01', 27, 7, 1),
(544, 'BHG14_3_Pieringer - HMZ Tamara Pieringer', 840.69, 764.26, 76.43, '10', 'miete', 0, '2025-12-01', 20, 4, 1),
(545, 'BHG14_3_Pieringer - BK Tamara Pieringer', 193.92, 176.29, 17.63, '10', 'bk', 0, '2025-12-01', 24, 4, 1),
(546, 'BHG14_3_Pieringer - Heizung Tamara Pieringer', 33.91, 28.26, 5.65, '20', 'heizung', 0, '2025-12-01', 23, 4, 1),
(547, 'BHG14_1_Fuchs - BK Frieda Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-12-03', 24, 2, 1),
(548, 'BHG14_1_Fuchs - Heizung Frieda Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-12-03', 23, 2, 1),
(549, 'BHG14_SP5_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-12-01', 27, 10, 1),
(550, 'BHG14_SP6_Bondar - HMZ Anna Bondar', 41.99, 34.99, 7.00, '20', 'miete', 0, '2025-12-01', 27, 11, 1),
(551, 'BHG14_2_Bondar - HMZ Anna Bondar', 840.99, 764.54, 76.45, '10', 'miete', 0, '2025-12-01', 20, 3, 1),
(552, 'BHG14_2_Bondar - BK Anna Bondar', 194.00, 176.36, 17.64, '10', 'bk', 0, '2025-12-01', 24, 3, 1),
(553, 'BHG14_2_Bondar - Heizung Anna Bondar', 33.92, 28.27, 5.65, '20', 'heizung', 0, '2025-12-01', 23, 3, 1),
(555, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-08-29', 26, NULL, 1),
(556, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-07-31', 26, NULL, 1),
(557, 'EVN', 55.38, 46.15, 9.23, '20', 'strom', 1, '2025-09-16', 26, NULL, 1),
(558, 'EVN', 61.00, 50.83, 10.17, '20', 'strom', 1, '2025-09-23', 26, NULL, 1),
(559, 'EVN', 68.19, 56.83, 11.36, '20', 'strom', 1, '2025-12-09', 26, NULL, 1),
(560, 'BHG14_1_Fuchs - Heizung Frieda Fuchs', 25.19, 20.99, 4.20, '20', 'heizung', 0, '2025-09-05', 23, 2, 1),
(561, 'BHG14_1_Fuchs - BK Frieda Fuchs', 144.01, 130.92, 13.09, '10', 'bk', 0, '2025-09-05', 24, 2, 1),
(562, 'Nachverrechnung Miete BHG14_3', 118.85, 108.05, 10.80, '10', 'miete', 0, '2025-08-04', 20, 4, 1),
(563, 'Nachzahlung BK Heizung', -35.63, -29.69, -5.94, '20', 'heizung', 0, '2025-10-31', 23, 4, 1),
(564, 'Nachzahlung BK BHG14_3', 56.33, 51.21, 5.12, '10', 'bk', 0, '2025-10-28', 24, 4, 1),
(565, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-09-30', 26, NULL, 1),
(566, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-10-31', 26, NULL, 1),
(567, 'Hausbesorger', 240.00, 240.00, 0.00, '0', 'bk', 1, '2025-11-28', 26, NULL, 1),
(568, 'Hausbesorger', 120.00, 120.00, 0.00, '0', 'bk', 1, '2025-12-31', 26, NULL, 1),
(569, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-09-30', 26, NULL, 1),
(570, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-10-31', 26, NULL, 1),
(571, 'Sozialversicherungsbeiträge', 14.19, 14.19, 0.00, '0', 'bk', 1, '2025-11-28', 26, NULL, 1),
(572, 'Sozialversicherungsbeiträge', 7.10, 7.10, 0.00, '0', 'bk', 1, '2025-12-31', 26, NULL, 1),
(573, 'Grundsteuer B', 80.40, 0.00, 0.00, '0', 'bk', 1, '2025-02-10', 26, NULL, 1),
(574, 'Wasserbezugsgebühr', 20.90, 19.00, 1.90, '10', 'wasser', 1, '2025-02-10', 26, NULL, 1),
(575, 'WasserBereitstellungsgebühr', 31.35, 28.50, 2.85, '10', 'wasser', 1, '2025-02-10', 26, NULL, 1),
(576, 'NÖ Seuchenvorsorgeabgabe', 7.05, 7.05, 0.00, '0', 'bk', 1, '2025-02-10', 26, NULL, 1),
(577, 'Kanalbenutzungsgebühr', 271.99, 247.27, 24.73, '10', 'bk', 1, '2025-02-10', 26, NULL, 1),
(578, 'Abfallwirtschaftsabgabe', 29.76, 27.05, 2.71, '10', 'bk', 1, '2025-02-10', 26, NULL, 1),
(579, 'Abfallwirtschaftsgebühr', 175.00, 159.09, 15.91, '10', 'bk', 1, '2025-02-10', 26, NULL, 1),
(580, 'Abfallwirtschaftsgebühr', 169.02, 153.65, 15.37, '10', 'bk', 1, '2025-05-12', 26, NULL, 1),
(581, 'Grundsteuer B', 80.40, 0.00, 0.00, '0', 'bk', 1, '2025-08-05', 26, NULL, 1),
(582, 'Wasserbezugsgebühr', 20.90, 19.00, 1.90, '10', 'wasser', 1, '2025-08-05', 26, NULL, 1),
(583, 'WasserBereitstellungsgebühr', 34.65, 31.50, 3.15, '10', 'wasser', 1, '2025-08-05', 26, NULL, 1),
(584, 'Kanalbenutzungsgebühr', 271.99, 247.27, 24.73, '10', 'bk', 1, '2025-08-05', 26, NULL, 1),
(585, 'Abfallwirtschaftsgebühr', 133.27, 121.15, 12.12, '10', 'bk', 1, '2025-08-05', 26, NULL, 1),
(586, 'Abfallwirtschaftsabgabe', 28.76, 22.66, 2.06, '10', 'bk', 1, '2025-08-05', 26, NULL, 1),
(587, 'NÖ Seuchenvorsorgeabgabe', 7.05, 7.05, 0.00, '0', 'bk', 1, '2025-08-05', 26, NULL, 1),
(588, 'Grundsteuer B', 80.40, 0.00, 0.00, '0', 'bk', 1, '2025-11-17', 26, NULL, 1),
(589, 'Wasserbezugsgebühr', 151.80, 138.00, 13.80, '10', 'wasser', 1, '2025-11-17', 26, NULL, 1),
(590, 'Wasserbezugsgebühr', 468.90, 426.27, 42.63, '10', 'wasser', 1, '2025-11-17', 26, NULL, 1),
(591, 'WasserBereitstellungsgebühr', 34.65, 31.50, 3.15, '10', 'wasser', 1, '2025-11-17', 26, NULL, 1),
(592, 'Kanalbenutzungsgebühr', 271.99, 247.27, 24.73, '10', 'bk', 1, '2025-11-17', 26, NULL, 1),
(593, 'Abfallwirtschaftsgebühr', 133.27, 121.15, 12.12, '10', 'bk', 1, '2025-11-17', 26, NULL, 1),
(594, 'Abfallwirtschaftsabgabe', 22.66, 20.60, 2.06, '10', 'bk', 1, '2025-11-17', 26, NULL, 1),
(595, 'NÖ Seuchenvorsorgeabgabe', 7.05, 7.05, 0.00, '0', 'bk', 1, '2025-11-17', 26, NULL, 1),
(596, 'Aufrollung Gemeindeabgaben Abfall', -22.31, -20.28, -2.03, '10', 'bk', 1, '2025-11-13', 26, NULL, 1),
(597, 'Bankimport #64: Frieda Fuchs', 169.20, 169.20, 0.00, '0', 'bk', 0, '2026-01-05', NULL, 2, 1);

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `dateien`
--

CREATE TABLE `dateien` (
  `id` int(11) NOT NULL,
  `user_defined_name` varchar(255) NOT NULL,
  `notizen` text DEFAULT NULL,
  `original_filename` varchar(255) NOT NULL,
  `stored_filename` varchar(255) NOT NULL,
  `file_path` varchar(255) NOT NULL,
  `mime_type` varchar(100) NOT NULL,
  `file_size` int(11) NOT NULL,
  `upload_datum` timestamp NULL DEFAULT current_timestamp(),
  `einheit_id` int(11) DEFAULT NULL,
  `liegenschaft_id` int(11) DEFAULT NULL,
  `mietvertrag_id` int(11) DEFAULT NULL,
  `mieter_id` int(11) DEFAULT NULL,
  `meter_id` int(11) DEFAULT NULL,
  `zaehlerstand_id` int(11) DEFAULT NULL,
  `typ` varchar(20) DEFAULT 'upload'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `dateien`
--

INSERT INTO `dateien` (`id`, `user_defined_name`, `notizen`, `original_filename`, `stored_filename`, `file_path`, `mime_type`, `file_size`, `upload_datum`, `einheit_id`, `liegenschaft_id`, `mietvertrag_id`, `mieter_id`, `meter_id`, `zaehlerstand_id`, `typ`) VALUES
(12, 'VPI2020_WertSicherung_Template', NULL, 'wertsicherung_template.docx', 'vorlage_686d163f9e7c49.19241010.docx', 'vorlagen/vorlage_686d163f9e7c49.19241010.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 22558, '2025-07-08 12:59:43', NULL, NULL, NULL, NULL, NULL, NULL, 'template'),
(15, 'Beibblatt BK Abrechnung Wasser', '', 'bk_wasser_beiblat_template.docx', 'vorlage_686d38735897e0.13004834.docx', 'vorlagen/vorlage_686d38735897e0.13004834.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 20975, '2025-07-08 15:25:39', NULL, NULL, NULL, NULL, NULL, NULL, 'template'),
(32, 'BK Abrechnung 2025 LEH265', '', 'LEH265_BK_Abrechnung.pdf', 'file_68832a2f6648b4.37448037.pdf', 'files/file_68832a2f6648b4.37448037.pdf', 'application/pdf', 2649021, '2025-07-25 06:54:39', 1, NULL, NULL, NULL, NULL, NULL, 'upload'),
(33, 'BK Abrechnung 2025 LEH 2511', '', 'BK_Abrechung_LEH2511.pdf', 'file_68832c7912e973.26523732.pdf', 'files/file_68832c7912e973.26523732.pdf', 'application/pdf', 3043618, '2025-07-25 07:04:25', 12, NULL, NULL, NULL, NULL, NULL, 'upload'),
(34, 'EVN Vertragsbestätigung PV', '', '20250701_EVN_Vertragsbestätigung.pdf', 'file_6883324ce736b3.20151699.pdf', 'files/file_6883324ce736b3.20151699.pdf', 'application/pdf', 4413271, '2025-07-25 07:29:16', NULL, 1, NULL, NULL, NULL, NULL, 'upload'),
(35, 'EVN PV Betriebserlaubnis', '', '20250306_EVN Erteilung der Betriebserlaubnis Typ A_06.03.2025 08_57_20.pdf', 'file_6883327e2f5dd4.35691061.pdf', 'files/file_6883327e2f5dd4.35691061.pdf', 'application/pdf', 44316, '2025-07-25 07:30:06', NULL, 1, NULL, NULL, NULL, NULL, 'upload'),
(36, 'Netz-NÖ Netzzugangsvertrag', '', '20241003_Netzzugangsvertrag Bestätigungsschreiben_03.10.2024 07_05_05.pdf', 'file_688332dab42695.05099746.pdf', 'files/file_688332dab42695.05099746.pdf', 'application/pdf', 51722, '2025-07-25 07:31:38', NULL, 1, NULL, NULL, NULL, NULL, 'upload'),
(39, 'BK full template', NULL, 'bk_full_template.docx', 'vorlage_6888bafbab0536.19745666.docx', 'vorlagen/vorlage_6888bafbab0536.19745666.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 21014, '2025-07-29 12:13:47', NULL, NULL, NULL, NULL, NULL, NULL, 'template'),
(60, 'Mietvertrag', '', '20240819_LEH265_Mietvertrag_unterschrieben.pdf', 'file_68978d5ba1f903.25817970.pdf', 'files/file_68978d5ba1f903.25817970.pdf', 'application/pdf', 4139924, '2025-08-09 18:03:07', NULL, NULL, 1, NULL, NULL, NULL, 'upload'),
(61, 'Wertsicherung ohne Nachverrechnung', NULL, 'wertsicherung_template_keine_nachzahlung.docx', 'vorlage_689c1a99551b79.13457765.docx', 'vorlagen/vorlage_689c1a99551b79.13457765.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 22667, '2025-08-13 04:54:49', NULL, NULL, NULL, NULL, NULL, NULL, 'template'),
(62, 'LEH265_Reicher_Wertsicherung', 'Serienbrief Wertsicherung', 'LEH265_Reicher_Wertsicherung_20250809_192300.docx', 'LEH265_Reicher_Wertsicherung_20250809_192300.docx', 'files/LEH265_Reicher_Wertsicherung_20250809_192300.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 21646, '2025-08-09 19:23:00', NULL, NULL, 1, NULL, NULL, NULL, 'upload'),
(83, 'MV Verlängerung bis Oktober 2028', '', 'MV Verlängerung bis 31.10.2028 Demirez.pdf', 'file_68b83c88124649.02251188.pdf', 'files/file_68b83c88124649.02251188.pdf', 'application/pdf', 595363, '2025-09-03 13:03:04', NULL, NULL, 2, NULL, NULL, NULL, 'upload'),
(84, 'Vorschreibung 2025 09', '', '13_2025_Meidlinger Haupt 69_Top 5_Vorschreibung Dauer_092025.pdf', 'file_68b83d4bb32849.37803079.pdf', 'files/file_68b83d4bb32849.37803079.pdf', 'application/pdf', 143995, '2025-09-03 13:06:19', NULL, NULL, 12, NULL, NULL, NULL, 'upload'),
(85, 'Vorschreibung ab 2025 10', '', '14_2025_Meidlinger Haupt 69_Top 5_Vorschreibung Dauer_102025.pdf', 'file_68b83d6692a474.95032643.pdf', 'files/file_68b83d6692a474.95032643.pdf', 'application/pdf', 148970, '2025-09-03 13:06:46', NULL, NULL, 12, NULL, NULL, NULL, 'upload'),
(89, 'MEG_Wersicherung_fix', NULL, 'MEG_fixed_wertsicherung_template(1).docx', 'vorlage_69358c28628047.17107807.docx', 'vorlagen/vorlage_69358c28628047.17107807.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 21754, '2025-12-07 14:16:08', NULL, NULL, NULL, NULL, NULL, NULL, 'template'),
(95, 'LEH25_11_Demirez_Wertsicherung', 'Serienbrief Wertsicherung', 'LEH25_11_Demirez_Wertsicherung_20251204_135926.pdf', 'LEH25_11_Demirez_Wertsicherung_20251204_135926.pdf', 'files/LEH25_11_Demirez_Wertsicherung_20251204_135926.pdf', 'application/pdf', 26041, '2025-12-04 13:59:28', NULL, NULL, 2, NULL, NULL, NULL, 'upload'),
(96, 'Vorschreibung', '', '16_2025_Meidlinger Haupt 69_Top 5_Vorschreibung Dauer_012026.pdf', 'file_694eb9d98ba555.08657547.pdf', 'files/file_694eb9d98ba555.08657547.pdf', 'application/pdf', 145336, '2025-12-26 16:37:45', NULL, NULL, 12, NULL, NULL, NULL, 'upload'),
(97, 'bk_abrechnung test', NULL, 'bk_abrechnung_test.docx', 'vorlage_69541c6723ba14.39257523.docx', 'vorlagen/vorlage_69541c6723ba14.39257523.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 16831, '2025-12-30 18:39:35', NULL, NULL, NULL, NULL, NULL, NULL, 'template'),
(98, 'Vorschreibung_LEH2511', 'RechnungundVorschreibung LEH2511', 'Rechnung-02252-0041-002-2026-1-Fuchs-Martina-.pdf', 'file_696118cc96fd93.44895863.pdf', 'files/file_696118cc96fd93.44895863.pdf', 'application/pdf', 190159, '2026-01-09 15:03:40', 12, NULL, NULL, NULL, NULL, NULL, 'upload'),
(99, 'bk_abrechnung_neu_gemini', NULL, 'bk_abrechnung_neu_gemini(1).docx', 'vorlage_697f23d440f120.14415398.docx', 'vorlagen/vorlage_697f23d440f120.14415398.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 15635, '2026-02-01 09:58:44', NULL, NULL, NULL, NULL, NULL, NULL, 'template');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `eigentuemer`
--

CREATE TABLE `eigentuemer` (
  `id` int(11) NOT NULL,
  `anrede` varchar(10) DEFAULT NULL,
  `vorname` varchar(100) NOT NULL,
  `nachname` varchar(100) NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `telefon` varchar(20) DEFAULT NULL,
  `adresse` varchar(255) DEFAULT NULL,
  `plz` varchar(10) DEFAULT NULL,
  `ort` varchar(100) DEFAULT NULL,
  `iban` varchar(34) DEFAULT NULL,
  `notizen` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `eigentuemer`
--

INSERT INTO `eigentuemer` (`id`, `anrede`, `vorname`, `nachname`, `email`, `telefon`, `adresse`, `plz`, `ort`, `iban`, `notizen`) VALUES
(1, 'Frau', 'Martina', 'Fuchs', 'martinafuchs1978@gmail.com', '+436642404035', 'Föhrengasse 35', '3423', 'St. Andrä-Wördern', 'AT', ''),
(2, 'Herr', 'Thomas', 'Fuchs', 'fuchst@gmail.com', '+4368120258057', 'Föhrengasse 35', '3423', 'St. Andrä-Wördern', 'AT', '');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `einheiten`
--

CREATE TABLE `einheiten` (
  `id` int(11) NOT NULL,
  `name` varchar(255) NOT NULL,
  `typ` enum('Wohnung','Parkplatz','Sonstiges') NOT NULL,
  `top` varchar(50) NOT NULL,
  `nutzflaeche` decimal(6,2) DEFAULT 0.00,
  `bkanteil` decimal(6,2) DEFAULT 0.00,
  `notizen` text DEFAULT NULL,
  `liegenschaft_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `einheiten`
--

INSERT INTO `einheiten` (`id`, `name`, `typ`, `top`, `nutzflaeche`, `bkanteil`, `notizen`, `liegenschaft_id`) VALUES
(1, 'LEH26_5', 'Wohnung', '5', 75.00, 100.00, 'Ehemalige Wohnung meiner Mama!', 2),
(2, 'BHG14_1', 'Wohnung', '1', 55.26, 20.99, NULL, 1),
(3, 'BHG14_2', 'Wohnung', '2', 77.43, 28.27, NULL, 1),
(4, 'BHG14_3', 'Wohnung', '3', 76.43, 28.26, NULL, 1),
(5, 'BHG14_4', 'Wohnung', '4', 54.48, 22.48, NULL, 1),
(6, 'BHG14_SP1', 'Parkplatz', 'SP1', 0.00, 0.00, NULL, 1),
(7, 'BHG14_SP2', 'Parkplatz', 'SP2', 0.00, 0.00, NULL, 1),
(8, 'BHG14_SP3', 'Parkplatz', 'SP3', 0.00, 0.00, NULL, 1),
(9, 'BHG14_SP4', 'Parkplatz', 'SP4', 0.00, 0.00, NULL, 1),
(10, 'BHG14_SP5', 'Parkplatz', 'SP5', 0.00, 0.00, NULL, 1),
(11, 'BHG14_SP6', 'Parkplatz', 'SP6', 0.00, 0.00, NULL, 1),
(12, 'LEH25_11', 'Wohnung', '11', 77.11, 100.00, 'In Besitz seit 2016. Vermietet über MEG. ', 3),
(14, 'MHS69_5', 'Wohnung', '5', 51.77, 100.00, 'Von Petra Auenheimer Freundin gekauft, 100k von Timmy Oma an Eric geschenkt', 5);

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `journal`
--

CREATE TABLE `journal` (
  `id` int(11) NOT NULL,
  `uuid` varchar(36) NOT NULL,
  `datum` date NOT NULL,
  `mieter_id` int(11) DEFAULT NULL,
  `kategorie` enum('FORDERUNG','ZAHLUNG','ERLOES_MIETE','ERLOES_BK','ERLOES_HEIZUNG','STEUER','SONSTIGES') NOT NULL,
  `betrag` decimal(15,2) NOT NULL,
  `kommentar` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `journal`
--

INSERT INTO `journal` (`id`, `uuid`, `datum`, `mieter_id`, `kategorie`, `betrag`, `kommentar`) VALUES
(1, 'c30b90e0-76ab-49a2-b3f1-3ee7a5bb3d29', '2026-01-07', 17, 'FORDERUNG', 41.99, 'Bankimport #61: Greiner  Brigitte'),
(2, 'c30b90e0-76ab-49a2-b3f1-3ee7a5bb3d29', '2026-01-07', 17, 'FORDERUNG', -41.99, 'Ausgleich Forderung'),
(3, '7ffbfc24-08eb-4612-95b3-a6fd4d5605c2', '2026-01-27', NULL, 'FORDERUNG', -535.53, 'Bankimport'),
(4, '7ffbfc24-08eb-4612-95b3-a6fd4d5605c2', '2026-01-27', NULL, 'FORDERUNG', 535.53, '3007903064 St. Andrae-Woerdern, Bah ngasse 14 ABR 716080034379 115,29 A BR 716080034380 152,81 ABR 71608003 4381 267,43 | Sachkonto #26'),
(5, '415be7ee-6fe8-4de3-9331-610782050062', '2026-01-05', 11, 'FORDERUNG', 169.20, 'Bankimport #64: Frieda Fuchs'),
(6, '415be7ee-6fe8-4de3-9331-610782050062', '2026-01-05', 11, 'FORDERUNG', -169.20, 'Ausgleich Forderung');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `liegenschaften`
--

CREATE TABLE `liegenschaften` (
  `id` int(11) NOT NULL,
  `name` varchar(255) NOT NULL,
  `plz` varchar(10) NOT NULL,
  `ort` varchar(255) NOT NULL,
  `adresse` varchar(255) NOT NULL,
  `notizen` text DEFAULT NULL,
  `eigentuemer1_id` int(11) DEFAULT NULL,
  `eigentuemer2_id` int(11) DEFAULT NULL,
  `heat_usage_percent` decimal(5,2) NOT NULL DEFAULT 85.00
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `liegenschaften`
--

INSERT INTO `liegenschaften` (`id`, `name`, `plz`, `ort`, `adresse`, `notizen`, `eigentuemer1_id`, `eigentuemer2_id`, `heat_usage_percent`) VALUES
(1, 'BHG14', '3423', 'St. Andrä-Wördern', 'Bahngasse 14', 'Gebaut von den Großeltern. Umgebaut und vermietet von uns. ', 1, NULL, 85.00),
(2, 'LEH26', '3423', 'St. Andrä-Wördern', 'Lehnergasse 2/6', 'Haus mit der Wohnung meiner Mutter', 2, NULL, 85.00),
(3, 'LEH25', '3423', 'St. Andrä-Wördern', 'Lehnergasse 2/5', 'Erst Wohnung in Lehnergasse. Ist nicht in Immo-Fuchs KG sondern als Eigentümer Gemeinschaft.', 1, 2, 85.00),
(5, 'MHS69', '1120', 'Wien', 'Meidlinger Hauptstrasse 69', 'Von Petra Auenheimer gekauft.', 1, 2, 85.00);

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `mieter`
--

CREATE TABLE `mieter` (
  `id` int(11) NOT NULL,
  `anrede` enum('Herr','Frau') NOT NULL,
  `vorname` varchar(100) DEFAULT NULL,
  `nachname` varchar(100) DEFAULT NULL,
  `gebdatum` date DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `telefon` varchar(30) DEFAULT NULL,
  `bank_account_id` varchar(64) DEFAULT NULL,
  `notizen` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `mieter`
--

INSERT INTO `mieter` (`id`, `anrede`, `vorname`, `nachname`, `gebdatum`, `email`, `telefon`, `bank_account_id`, `notizen`) VALUES
(11, 'Frau', 'Frieda', 'Fuchs', '1958-06-01', 'frieda.fuchs@gmail.com', '+4369981623430', 'AT792011122612019300', 'Hausbesorgerin'),
(12, 'Frau', 'Anna', 'Bondar', '1983-04-16', 'bondar.anna@icloud.com', '+436609637501', 'AT472011184580265400', ''),
(13, 'Herr', 'Bogdan', 'Bondar', '1983-10-03', NULL, NULL, '', ''),
(14, 'Frau', 'Petra', 'Steinkogler', '1991-03-13', 'petra.steinkogler@posteo.de', '+436801434942', 'AT343438000006222343', ''),
(15, 'Frau', 'Katharina', 'Reicher', '1987-10-30', 'skorpion325@hotmail.com', '+436604083760', 'AT501200010013537708', ''),
(16, 'Frau', 'Tamara', 'Pieringer', '1973-06-28', 'tamarapieringer@icloud.com', '+4367762920290', 'AT824300000005702303', ''),
(17, 'Frau', 'Brigitte', 'Grainer', '1954-06-15', 'brigittegreiner54@gmail.com', '+436648602325', 'AT313288000007005994', ''),
(18, 'Herr', 'Israfil', 'Demirez', '1978-05-04', NULL, NULL, NULL, ''),
(24, 'Frau', 'Jerica', 'Steklasa', '1992-03-16', 'jerica.steklasa@gmail.com', '', 'AT362011129711349000', ''),
(25, 'Herr', 'Macpherson', 'Ugochukwu Chikwereuba', '1991-12-22', '', '', '', '');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `mietervertrag`
--

CREATE TABLE `mietervertrag` (
  `id` int(11) NOT NULL,
  `name` varchar(255) NOT NULL,
  `einzugsdatum` date DEFAULT NULL,
  `auszugsdatum` date DEFAULT NULL,
  `wertsicherung` date DEFAULT NULL,
  `wertsicherung_typ` enum('vpi','fix') NOT NULL DEFAULT 'vpi',
  `wertsicherung_faktor` decimal(8,3) DEFAULT NULL,
  `vpi2020` decimal(10,2) DEFAULT NULL,
  `hmz` decimal(10,2) DEFAULT NULL,
  `hmzm2` decimal(10,2) DEFAULT NULL,
  `bknetto` decimal(10,2) DEFAULT NULL,
  `heizungnetto` decimal(10,2) DEFAULT NULL,
  `bruttomiete` decimal(10,2) DEFAULT NULL,
  `kaution` decimal(10,2) DEFAULT NULL,
  `notiz` text DEFAULT NULL,
  `mieter_id` int(11) DEFAULT NULL,
  `mieter2_id` int(11) DEFAULT NULL,
  `einheit_id` int(11) DEFAULT NULL,
  `verwalter_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `mietervertrag`
--

INSERT INTO `mietervertrag` (`id`, `name`, `einzugsdatum`, `auszugsdatum`, `wertsicherung`, `wertsicherung_typ`, `wertsicherung_faktor`, `vpi2020`, `hmz`, `hmzm2`, `bknetto`, `heizungnetto`, `bruttomiete`, `kaution`, `notiz`, `mieter_id`, `mieter2_id`, `einheit_id`, `verwalter_id`) VALUES
(1, 'LEH26_5_Reicher', '2024-09-01', '2027-08-31', '2026-09-01', 'vpi', NULL, 123.80, 600.11, 7.78, 216.82, 0.00, 898.62, 2640.00, '', 15, NULL, 1, 2),
(2, 'LEH25_11_Demirez', '2019-11-01', '2028-10-31', '2027-01-01', 'fix', 1.500, NULL, 571.22, 1.00, 233.90, 0.00, 828.51, 2880.00, 'Jährliche Wertsicherung am 01.01 um 1,5%', 18, NULL, 12, 3),
(3, 'BHG14_1_Fuchs', '2024-06-01', '2029-05-30', '2029-05-30', 'vpi', NULL, 120.30, 0.00, 5.23, 130.92, 20.99, 169.20, 0.00, 'Miete 5 Jahre im Voraus bezahlt. Hausmeister. ', 11, NULL, 2, 2),
(4, 'BHG14_2_Bondar', '2024-06-01', '2029-05-30', '2026-03-01', 'vpi', NULL, 123.80, 764.54, 6.94, 176.36, 28.27, 1068.91, 3140.00, 'Anna & Bogdan Bondar und 2 Kinder. ', 12, 13, 3, 2),
(5, 'BHG14_3_Pieringer', '2024-06-01', '2029-05-30', '2026-03-01', 'vpi', NULL, 123.80, 764.26, 6.94, 176.29, 28.26, 1068.52, 3140.00, 'Pieringer und Mutter Grainer', 16, 17, 4, 2),
(6, 'BHG14_4_Steinkogler', '2024-06-01', '2029-05-31', '2026-03-01', 'vpi', NULL, 123.80, 608.06, 6.94, 140.24, 22.48, 850.11, 2500.00, '', 14, NULL, 5, 2),
(7, 'BHG14_SP2_Pieringer', '2024-07-01', '2029-06-30', '2026-03-01', 'vpi', NULL, 123.80, 34.99, 0.00, 0.00, 0.00, 41.99, 125.00, '', 16, 17, 7, 2),
(8, 'BHG14_SP5_Bondar', '2024-06-01', '2029-05-30', '2026-03-01', 'vpi', NULL, 123.80, 34.99, 0.00, 0.00, 0.00, 41.99, 125.00, '', 12, 13, 10, 2),
(9, 'BHG14_SP6_Bondar', '2024-06-01', '2029-05-30', '2026-03-01', 'vpi', NULL, 123.80, 34.99, 0.00, 0.00, 0.00, 41.99, 125.00, '', 12, 13, 11, 2),
(12, 'MHS69_5_Steklasa', '2024-02-01', '2027-02-28', '2027-01-01', 'vpi', NULL, 122.60, 363.69, NULL, 207.25, 70.00, NULL, 2100.00, '', 24, 25, 14, 2);

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `miete_konto`
--

CREATE TABLE `miete_konto` (
  `id` int(11) NOT NULL,
  `mietervertrag_id` int(11) NOT NULL,
  `period` date NOT NULL,
  `type` enum('CHARGE','PAYMENT','CARRY','WARN') NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `note` varchar(255) DEFAULT NULL,
  `source_table` varchar(50) DEFAULT NULL,
  `source_id` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `miete_konto`
--

INSERT INTO `miete_konto` (`id`, `mietervertrag_id`, `period`, `type`, `amount`, `note`, `source_table`, `source_id`, `created_at`) VALUES
(68, 3, '2025-08-05', 'PAYMENT', 169.20, 'Frieda Fuchs BK Top1 Frieda Fuchs', 'auszuege', 444, '2025-08-09 07:32:43'),
(69, 5, '2025-08-05', 'PAYMENT', 1068.52, 'Greiner  Brigitte Miete Bahngasse 14/Top 3', 'auszuege', 445, '2025-08-09 07:32:43'),
(70, 5, '2025-08-05', 'PAYMENT', 41.99, 'Greiner  Brigitte Kfz-Stellplatz Nr. 2', 'auszuege', 446, '2025-08-09 07:32:43'),
(71, 4, '2025-08-04', 'PAYMENT', 83.98, 'Anna Bondar Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Juli 2025)', 'auszuege', 447, '2025-08-09 07:32:43'),
(72, 4, '2025-08-04', 'PAYMENT', 1068.91, 'Anna Bondar Mietvertrag, Juli 2025, Bahngasse 1 4/Top 2', 'auszuege', 448, '2025-08-09 07:32:43'),
(73, 6, '2025-08-04', 'PAYMENT', 850.11, 'Steinkogler  Petra Miete Top4 Steinkogler', 'auszuege', 449, '2025-08-09 07:32:43'),
(74, 5, '2025-08-04', 'PAYMENT', 118.85, 'Mag. Tamara Pieringer Nachverrechnung', 'auszuege', 450, '2025-08-09 07:32:43'),
(75, 1, '2025-08-01', 'PAYMENT', 892.41, 'Katharina Reicher Miete juli 2025', 'auszuege', 453, '2025-08-09 07:32:43'),
(76, 2, '2025-08-15', 'PAYMENT', 828.51, 'Manuell: Konto Martina', NULL, NULL, '2025-08-09 08:02:10'),
(77, 1, '2025-08-01', 'CHARGE', -892.41, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(78, 2, '2025-08-01', 'CHARGE', -828.51, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(79, 3, '2025-08-01', 'CHARGE', -169.20, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(80, 4, '2025-08-01', 'CHARGE', -1068.91, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(81, 5, '2025-08-01', 'CHARGE', -1068.52, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(82, 6, '2025-08-01', 'CHARGE', -850.11, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(83, 7, '2025-08-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(84, 8, '2025-08-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(85, 9, '2025-08-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-08-09 12:02:20'),
(86, 5, '2025-08-01', 'CHARGE', -118.85, 'Manuell: Wertsicherung', NULL, NULL, '2025-08-09 12:28:34'),
(88, 1, '2025-09-01', 'CHARGE', -898.62, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(89, 2, '2025-09-01', 'CHARGE', -828.51, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(90, 3, '2025-09-01', 'CHARGE', -169.20, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(91, 4, '2025-09-01', 'CHARGE', -1068.91, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(92, 4, '2025-09-01', 'CARRY', 83.98, 'Carry forward', NULL, NULL, '2025-09-01 06:00:01'),
(93, 5, '2025-09-01', 'CHARGE', -1068.52, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(94, 5, '2025-09-01', 'CARRY', 41.99, 'Carry forward', NULL, NULL, '2025-09-01 06:00:01'),
(95, 6, '2025-09-01', 'CHARGE', -850.11, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(96, 7, '2025-09-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(97, 7, '2025-09-01', 'CARRY', -41.99, 'Carry forward', NULL, NULL, '2025-09-01 06:00:01'),
(98, 8, '2025-09-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(99, 8, '2025-09-01', 'CARRY', -41.99, 'Carry forward', NULL, NULL, '2025-09-01 06:00:01'),
(100, 9, '2025-09-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(101, 9, '2025-09-01', 'CARRY', -41.99, 'Carry forward', NULL, NULL, '2025-09-01 06:00:01'),
(102, 12, '2025-09-01', 'CHARGE', 0.00, 'Monthly rent', NULL, NULL, '2025-09-01 06:00:01'),
(103, 3, '2025-09-05', 'PAYMENT', 169.20, 'Frieda Fuchs BK Top1 Frieda Fuchs', 'auszuege', 475, '2025-09-10 11:28:53'),
(104, 5, '2025-09-04', 'PAYMENT', 1068.52, 'Greiner  Brigitte Miete Bahngasse 14/Top 3', 'auszuege', 477, '2025-09-10 11:28:53'),
(105, 5, '2025-09-04', 'PAYMENT', 41.99, 'Greiner  Brigitte Kfz-Stellplatz Nr. 2', 'auszuege', 478, '2025-09-10 11:28:53'),
(106, 6, '2025-09-03', 'PAYMENT', 850.11, 'Steinkogler  Petra Miete Top4 Steinkogler', 'auszuege', 479, '2025-09-10 11:28:53'),
(107, 1, '2025-09-02', 'PAYMENT', 898.62, 'Katharina Reicher Miete August 2025', 'auszuege', 482, '2025-09-10 11:28:53'),
(108, 4, '2025-09-01', 'PAYMENT', 83.98, 'Anna Bondar Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Sep 2025)', 'auszuege', 483, '2025-09-10 11:28:53'),
(109, 4, '2025-09-01', 'PAYMENT', 1068.91, 'Anna Bondar Mietvertrag, Sep 2025, Bahngasse 14 /Top 2', 'auszuege', 484, '2025-09-10 11:28:53'),
(110, 2, '2025-09-15', 'PAYMENT', 828.51, 'Manuell: Manuell: Konto Martina', NULL, NULL, '2025-09-10 11:35:52'),
(111, 1, '2025-10-01', 'CHARGE', -898.62, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(112, 2, '2025-10-01', 'CHARGE', -828.51, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(113, 3, '2025-10-01', 'CHARGE', -169.20, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(114, 4, '2025-10-01', 'CHARGE', -1068.91, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(115, 4, '2025-10-01', 'CARRY', 251.94, 'Carry forward', NULL, NULL, '2025-10-01 06:00:01'),
(116, 5, '2025-10-01', 'CHARGE', -1068.52, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(117, 5, '2025-10-01', 'CARRY', 125.97, 'Carry forward', NULL, NULL, '2025-10-01 06:00:01'),
(118, 6, '2025-10-01', 'CHARGE', -850.11, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(119, 7, '2025-10-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(120, 7, '2025-10-01', 'CARRY', -125.97, 'Carry forward', NULL, NULL, '2025-10-01 06:00:01'),
(121, 8, '2025-10-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(122, 8, '2025-10-01', 'CARRY', -125.97, 'Carry forward', NULL, NULL, '2025-10-01 06:00:01'),
(123, 9, '2025-10-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(124, 9, '2025-10-01', 'CARRY', -125.97, 'Carry forward', NULL, NULL, '2025-10-01 06:00:01'),
(125, 12, '2025-10-01', 'CHARGE', 0.00, 'Monthly rent', NULL, NULL, '2025-10-01 06:00:01'),
(126, 1, '2025-11-01', 'CHARGE', -898.62, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(127, 1, '2025-11-01', 'CARRY', -898.62, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(128, 2, '2025-11-01', 'CHARGE', -828.51, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(129, 2, '2025-11-01', 'CARRY', -828.51, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(130, 3, '2025-11-01', 'CHARGE', -169.20, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(131, 3, '2025-11-01', 'CARRY', -169.20, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(132, 4, '2025-11-01', 'CHARGE', -1068.91, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(133, 4, '2025-11-01', 'CARRY', -565.03, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(134, 5, '2025-11-01', 'CHARGE', -1068.52, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(135, 5, '2025-11-01', 'CARRY', -816.58, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(136, 6, '2025-11-01', 'CHARGE', -850.11, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(137, 6, '2025-11-01', 'CARRY', -850.11, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(138, 7, '2025-11-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(139, 7, '2025-11-01', 'CARRY', -293.93, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(140, 8, '2025-11-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(141, 8, '2025-11-01', 'CARRY', -293.93, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(142, 9, '2025-11-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(143, 9, '2025-11-01', 'CARRY', -293.93, 'Carry forward', NULL, NULL, '2025-11-01 07:00:01'),
(144, 12, '2025-11-01', 'CHARGE', 0.00, 'Monthly rent', NULL, NULL, '2025-11-01 07:00:01'),
(145, 3, '2025-11-05', 'PAYMENT', 169.20, 'Frieda Fuchs BK Top1 Frieda Fuchs', 'auszuege', 501, '2025-11-05 13:31:01'),
(146, 4, '2025-11-04', 'PAYMENT', 83.98, 'Anna Bondar Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Nov 2025)', 'auszuege', 502, '2025-11-05 13:31:01'),
(147, 4, '2025-11-04', 'PAYMENT', 1068.91, 'Anna Bondar Mietvertrag, Nov 2025, Bahngasse 14 /Top 2', 'auszuege', 503, '2025-11-05 13:31:01'),
(148, 5, '2025-11-04', 'PAYMENT', 41.99, 'Greiner  Brigitte Kfz-Stellplatz Nr. 2', 'auszuege', 505, '2025-11-05 13:31:01'),
(149, 5, '2025-11-04', 'PAYMENT', 1068.52, 'Greiner  Brigitte Miete Bahngasse 14/Top 3', 'auszuege', 506, '2025-11-05 13:31:01'),
(150, 6, '2025-11-03', 'PAYMENT', 850.11, 'Steinkogler  Petra Miete Top4 Steinkogler', 'auszuege', 507, '2025-11-05 13:31:01'),
(151, 1, '2025-12-01', 'CHARGE', -898.62, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(152, 1, '2025-12-01', 'CARRY', -2695.86, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(153, 2, '2025-12-01', 'CHARGE', -828.51, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(154, 2, '2025-12-01', 'CARRY', -2485.53, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(155, 3, '2025-12-01', 'CHARGE', -169.20, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(156, 3, '2025-12-01', 'CARRY', -338.40, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(157, 4, '2025-12-01', 'CHARGE', -1068.91, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(158, 4, '2025-12-01', 'CARRY', -1046.08, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(159, 5, '2025-12-01', 'CHARGE', -1068.52, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(160, 5, '2025-12-01', 'CARRY', -1591.17, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(161, 6, '2025-12-01', 'CHARGE', -850.11, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(162, 6, '2025-12-01', 'CARRY', -1700.22, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(163, 7, '2025-12-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(164, 7, '2025-12-01', 'CARRY', -629.85, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(165, 8, '2025-12-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(166, 8, '2025-12-01', 'CARRY', -629.85, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(167, 9, '2025-12-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(168, 9, '2025-12-01', 'CARRY', -629.85, 'Carry forward', NULL, NULL, '2025-12-01 07:00:01'),
(169, 12, '2025-12-01', 'CHARGE', 0.00, 'Monthly rent', NULL, NULL, '2025-12-01 07:00:01'),
(170, 6, '2025-12-03', 'PAYMENT', 850.11, 'Steinkogler  Petra Miete Top4 Steinkogler', 'auszuege', 529, '2025-12-03 15:59:18'),
(171, 3, '2025-12-03', 'PAYMENT', 169.20, 'Frieda Fuchs BK Top1 Frieda Fuchs', 'auszuege', 530, '2025-12-03 15:59:18'),
(172, 4, '2025-12-01', 'PAYMENT', 83.98, 'Anna Bondar Bahngasse 14 / Kfz-Stellplatz Nr. 5 und 6 (Dec 2025)', 'auszuege', 534, '2025-12-03 15:59:18'),
(173, 4, '2025-12-01', 'PAYMENT', 1068.91, 'Anna Bondar Mietvertrag, Dec 2025, Bahngasse 14 /Top 2', 'auszuege', 535, '2025-12-03 15:59:18'),
(174, 1, '2026-01-01', 'CHARGE', -898.62, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(175, 1, '2026-01-01', 'CARRY', -6290.34, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(176, 2, '2026-01-01', 'CHARGE', -828.51, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(177, 2, '2026-01-01', 'CARRY', -5799.57, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(178, 3, '2026-01-01', 'CHARGE', -169.20, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(179, 3, '2026-01-01', 'CARRY', -676.80, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(180, 4, '2026-01-01', 'CHARGE', -1068.91, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(181, 4, '2026-01-01', 'CARRY', -2008.18, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(182, 5, '2026-01-01', 'CHARGE', -1068.52, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(183, 5, '2026-01-01', 'CARRY', -4250.86, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(184, 6, '2026-01-01', 'CHARGE', -850.11, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(185, 6, '2026-01-01', 'CARRY', -3400.44, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(186, 7, '2026-01-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(187, 7, '2026-01-01', 'CARRY', -1301.69, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(188, 8, '2026-01-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(189, 8, '2026-01-01', 'CARRY', -1301.69, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(190, 9, '2026-01-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(191, 9, '2026-01-01', 'CARRY', -1301.69, 'Carry forward', NULL, NULL, '2026-01-01 07:00:01'),
(192, 12, '2026-01-01', 'CHARGE', 0.00, 'Monthly rent', NULL, NULL, '2026-01-01 07:00:01'),
(193, 1, '2026-02-01', 'CHARGE', -898.62, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(194, 1, '2026-02-01', 'CARRY', -13479.30, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(195, 2, '2026-02-01', 'CHARGE', -828.51, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(196, 2, '2026-02-01', 'CARRY', -12427.65, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(197, 3, '2026-02-01', 'CHARGE', -169.20, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(198, 3, '2026-02-01', 'CARRY', -1522.80, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(199, 4, '2026-02-01', 'CHARGE', -1068.91, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(200, 4, '2026-02-01', 'CARRY', -5085.27, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(201, 5, '2026-02-01', 'CHARGE', -1068.52, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(202, 5, '2026-02-01', 'CARRY', -9570.24, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(203, 6, '2026-02-01', 'CHARGE', -850.11, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(204, 6, '2026-02-01', 'CARRY', -7650.99, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(205, 7, '2026-02-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(206, 7, '2026-02-01', 'CARRY', -2645.37, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(207, 8, '2026-02-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(208, 8, '2026-02-01', 'CARRY', -2645.37, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(209, 9, '2026-02-01', 'CHARGE', -41.99, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02'),
(210, 9, '2026-02-01', 'CARRY', -2645.37, 'Carry forward', NULL, NULL, '2026-02-01 07:00:02'),
(211, 12, '2026-02-01', 'CHARGE', 0.00, 'Monthly rent', NULL, NULL, '2026-02-01 07:00:02');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `sachkonten`
--

CREATE TABLE `sachkonten` (
  `id` int(10) NOT NULL,
  `kontonummer` decimal(5,0) NOT NULL,
  `kontokurztext` varchar(255) NOT NULL,
  `anmerkung` varchar(255) DEFAULT NULL,
  `liegenschaft_id` int(11) DEFAULT NULL,
  `einheit_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `sachkonten`
--

INSERT INTO `sachkonten` (`id`, `kontonummer`, `kontokurztext`, `anmerkung`, `liegenschaft_id`, `einheit_id`) VALUES
(20, 4851, 'Mieterlös Bahngasse 10%', 'BHG14', 1, NULL),
(21, 4852, 'Mieterlös Lehnergasse 10%', 'LEH265', 2, NULL),
(22, 4853, 'Betriebskostenerlös Lehnergasse 10%', 'LEH265', 2, NULL),
(23, 4855, 'Betriebskostenerlös Bahngasse 20%', 'BHG14', 1, NULL),
(24, 4856, 'Betriebskostenerlös Bahngasse 10%', 'BHG14', 1, NULL),
(25, 7410, 'Betriebskosten Lehnergasse', 'LEH265', 2, NULL),
(26, 7411, 'Betriebskosten Bahngasse', 'BHG14', 1, NULL),
(27, 4850, 'Mieterlös Bahngasse 20%', 'BHG14', 1, NULL);

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `settings`
--

CREATE TABLE `settings` (
  `id` int(11) NOT NULL,
  `name` varchar(64) NOT NULL,
  `value` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `settings`
--

INSERT INTO `settings` (`id`, `name`, `value`) VALUES
(1, 'admin-email', 'fuchst@gmail.com'),
(2, 'email', 'office@immo-fuchs.at'),
(3, 'vpi-reminder-months', '2'),
(4, 'mv-expiry-notice-months', '6'),
(6, 'miete-kontokorrent-email', 'fuchst@gmail.com'),
(7, 'mietvertraege-auslauf-email', 'fuchst@gmail.com'),
(8, 'check-dates-email', 'fuchst@gmail.com');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `todos`
--

CREATE TABLE `todos` (
  `id` int(11) NOT NULL,
  `text` varchar(255) NOT NULL,
  `done` tinyint(1) NOT NULL DEFAULT 0,
  `created_at` datetime DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `todos`
--

INSERT INTO `todos` (`id`, `text`, `done`, `created_at`) VALUES
(2, 'add expanses for 2025', 0, '2025-07-09 13:49:49'),
(3, 'check income and outcome in buchungen if all is corrct', 0, '2025-07-09 13:50:11'),
(4, 'dokumente uploaden', 0, '2025-07-09 13:51:40'),
(6, 'BK Abrechnung fertigstellen', 0, '2025-07-09 13:59:25'),
(7, 'A: User Dokumente download machen. Konzept, Umsetzung, QRCode mit link auf Brief drucken', 0, '2025-07-18 08:56:53'),
(8, 'A: Mahnwesen einbauen, Brief schicken usw. ', 0, '2025-07-22 08:43:12'),
(10, 'check if BK aufteilung nach nutzwert oder nutzfläche', 1, '2025-07-29 13:16:51'),
(12, 'einnahmen, hausbesorger, evn, erledigt, sozialabgaben', 0, '2026-01-06 09:17:58');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `verwalter`
--

CREATE TABLE `verwalter` (
  `id` int(11) NOT NULL,
  `firmenname` varchar(255) NOT NULL,
  `ansprechpartner` varchar(255) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `webseite` varchar(255) DEFAULT NULL,
  `firmenbuch_nr` varchar(50) DEFAULT NULL,
  `steuernummer` varchar(50) DEFAULT NULL,
  `steuer_modus` enum('KG','MEG') NOT NULL DEFAULT 'KG',
  `telefon` varchar(50) DEFAULT NULL,
  `adresse` varchar(255) DEFAULT NULL,
  `plz` varchar(10) DEFAULT NULL,
  `ort` varchar(100) DEFAULT NULL,
  `liegenschaft_id` int(11) DEFAULT NULL,
  `einheit_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `verwalter`
--

INSERT INTO `verwalter` (`id`, `firmenname`, `ansprechpartner`, `email`, `webseite`, `firmenbuch_nr`, `steuernummer`, `steuer_modus`, `telefon`, `adresse`, `plz`, `ort`, `liegenschaft_id`, `einheit_id`) VALUES
(2, 'Immo-Fuchs KG', 'Martina Fuchs', 'office@immo-fuchs.at', 'http://www.immo-fuchs.at', 'FN 592404 h', 'ATU78726489', 'KG', '+436642404035', 'Föhrengasse 35', '3423', 'St. Andrä-Wördern', 1, NULL),
(3, 'MEG Martina&Thomas Fuchs', 'Martina Fuchs', 'martinafuchs1978@gmail.com', '', '', '', 'MEG', '+436642404035', 'Föhrengasse 35', '3423', 'St. Andrä-Wördern', NULL, 12);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_allgemeinstrom_abrechnung`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_allgemeinstrom_abrechnung` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`einheit_id` int(11)
,`einheit_name` varchar(255)
,`mieter_namen` mediumtext
,`anteil_prozent` decimal(15,6)
,`total_kwh` decimal(55,3)
,`wp_kwh` decimal(55,3)
,`general_kwh` decimal(56,3)
,`price_per_kwh` decimal(39,6)
,`cost_general` decimal(65,9)
,`kosten_anteil` decimal(65,19)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_bk_verteilung`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_bk_verteilung` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`einheit_id` int(11)
,`einheit_name` varchar(255)
,`mieter_namen` mediumtext
,`einheit_bkanteil` decimal(6,2)
,`anteil_prozent` decimal(15,6)
,`anteil_euro` decimal(39,2)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_gesamtabrechnung`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_gesamtabrechnung` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`einheit_id` int(11)
,`einheit_name` varchar(255)
,`mieter_namen` mediumtext
,`cost_wasser` decimal(65,19)
,`cost_strom_allg` decimal(65,19)
,`cost_ww` decimal(65,23)
,`cost_heizung` decimal(65,32)
,`netto_10` decimal(65,23)
,`ust_10` decimal(65,25)
,`netto_20` decimal(65,32)
,`ust_20` decimal(65,34)
,`akonto_10` decimal(32,2)
,`akonto_20` decimal(32,2)
,`total_brutto` decimal(65,34)
,`total_akonto` decimal(33,2)
,`saldo` decimal(65,34)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_gesamtabrechnung_detail`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_gesamtabrechnung_detail` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`einheit_id` int(11)
,`einheit_name` varchar(255)
,`mieter_namen` mediumtext
,`cost_strom_allg` decimal(65,19)
,`cost_ww` decimal(65,23)
,`cost_heizung` decimal(65,32)
,`netto_10_total` decimal(65,23)
,`ust_10_total` decimal(65,25)
,`brutto_10_total` decimal(65,25)
,`akonto_10_brutto` decimal(32,2)
,`saldo_10` decimal(65,25)
,`netto_20_total` decimal(65,32)
,`ust_20_total` decimal(65,34)
,`brutto_20_total` decimal(65,34)
,`akonto_20_brutto` decimal(32,2)
,`saldo_20` decimal(65,34)
,`total_netto_costs` decimal(65,32)
,`total_brutto_costs` decimal(65,34)
,`total_saldo` decimal(65,34)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_heizung_abrechnung`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_heizung_abrechnung` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`einheit_id` int(11)
,`einheit_name` varchar(255)
,`mieter_namen` mediumtext
,`measured_kwh` decimal(55,3)
,`total_heizung_euro` decimal(65,16)
,`percent_config` decimal(5,2)
,`kosten_fix` decimal(65,32)
,`kosten_var` decimal(65,29)
,`preis_pro_kwh` decimal(65,26)
,`kosten_gesamt_netto` decimal(65,32)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_mieter_saldo`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_mieter_saldo` (
`mieter_id` int(11)
,`saldo` decimal(37,2)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_objekt_uebersicht`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_objekt_uebersicht` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`kosten_bk_netto` decimal(32,2)
,`kosten_strom_netto` decimal(32,2)
,`kosten_wasser_netto` decimal(32,2)
,`einnahmen_bk_netto` decimal(32,2)
,`einnahmen_heizung_netto` decimal(32,2)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_warmwasser_abrechnung`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_warmwasser_abrechnung` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`einheit_id` int(11)
,`einheit_name` varchar(255)
,`mieter_namen` mediumtext
,`measured_m3` decimal(55,3)
,`kosten_wp_gesamt` decimal(65,9)
,`kosten_pool_ww` decimal(65,16)
,`jaz` decimal(63,7)
,`ratio_ww` decimal(62,7)
,`price_per_m3` decimal(65,20)
,`kosten_netto` decimal(65,23)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_wasser_abrechnung`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_wasser_abrechnung` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`einheit_id` int(11)
,`einheit_name` varchar(255)
,`mieter_namen` mediumtext
,`verbrauch_gemessen` decimal(55,3)
,`anteil_schwund` decimal(65,13)
,`verbrauch_gesamt` decimal(65,13)
,`kosten_anteil` decimal(65,19)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_wp_metrics`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_wp_metrics` (
`liegenschaft_id` int(11)
,`jahr` int(5)
,`input_kwh` decimal(55,3)
,`output_heat_kwh` decimal(55,3)
,`output_ww_kwh` decimal(55,3)
,`total_output_kwh` decimal(56,3)
,`jaz` decimal(63,7)
,`ratio_ww` decimal(62,7)
,`ratio_heat` decimal(62,7)
);

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `view_zaehler_trend_vergleich`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `view_zaehler_trend_vergleich` (
`zaehler_id` int(11)
,`zaehlernummer` varchar(50)
,`zaehlertyp` enum('electricity','water_cold','water_hot','heat_energy','cool_energy','WP_heat','WP_electricity','WP_warmwater','electricity_PV')
,`liegenschaft_id` int(11)
,`einheit_id` int(11)
,`einheit_name` varchar(255)
,`einheit_top` varchar(50)
,`jahr` int(5)
,`verbrauch` decimal(33,3)
,`daily_avg` decimal(37,7)
,`tage` int(9)
,`prev_jahr` int(5)
,`prev_verbrauch` decimal(33,3)
,`prev_daily_avg` decimal(37,7)
,`trend_prozent` decimal(52,11)
);

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `zaehler`
--

CREATE TABLE `zaehler` (
  `id` int(11) NOT NULL,
  `zaehlernummer` varchar(50) DEFAULT NULL,
  `zaehlertyp` enum('electricity','water_cold','water_hot','heat_energy','cool_energy','WP_heat','WP_electricity','WP_warmwater','electricity_PV') NOT NULL,
  `kind` enum('reading','consumption') NOT NULL DEFAULT 'reading',
  `liegenschaft_id` int(11) DEFAULT NULL,
  `einheit_id` int(11) DEFAULT NULL,
  `description` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `zaehler`
--

INSERT INTO `zaehler` (`id`, `zaehlernummer`, `zaehlertyp`, `kind`, `liegenschaft_id`, `einheit_id`, `description`) VALUES
(1, '302835522', 'water_cold', 'reading', 1, 2, ''),
(2, '302815029', 'water_hot', 'reading', 1, 2, ''),
(3, '302835577', 'water_cold', 'reading', 1, 3, ''),
(4, '302815036', 'water_hot', 'reading', 1, 3, ''),
(5, '302835553', 'water_cold', 'reading', 1, 4, ''),
(6, '302815067', 'water_hot', 'reading', 1, 4, ''),
(7, '302835560', 'water_cold', 'reading', 1, 5, ''),
(8, '302815050', 'water_hot', 'reading', 1, 5, ''),
(9, '181210320061', 'electricity', 'reading', 1, 2, 'Zählpunknummer: AT0020000000000000000000100459123'),
(10, '181210224687', 'electricity', 'reading', 1, 3, 'Zählpunktnummer: AT0020000000000000000000020709657'),
(11, '181210224697', 'electricity', 'reading', 1, 4, 'Zählpunktnummer: AT0020000000000000000000100459128'),
(12, '181210068081 ', 'electricity', 'reading', 1, 5, 'Zählpunktnummer: AT0020000000000000000000100459129'),
(13, '178210307651', 'electricity', 'reading', 1, NULL, 'Zählpunktnummer: AT0020000000000000000000020709845'),
(14, '178210307651', 'electricity_PV', 'reading', 1, NULL, 'Zählpunktnummer: AT0020000000000000000000100450205\r\nPV-Einspeisung'),
(15, '5115-229001864', 'heat_energy', 'reading', 1, 2, ''),
(16, '5115-229001864', 'cool_energy', 'reading', 1, 2, ''),
(17, '51155-237006615', 'heat_energy', 'reading', 1, 3, ''),
(18, '51155-237006615', 'cool_energy', 'reading', 1, 3, ''),
(19, '51155-324051771', 'heat_energy', 'reading', 1, 4, ''),
(20, '51155-324051771', 'cool_energy', 'reading', 1, 4, ''),
(21, '5115-229001826', 'heat_energy', 'reading', 1, 5, ''),
(22, '5115-229001826', 'cool_energy', 'reading', 1, 5, ''),
(23, '21166067', 'water_cold', 'reading', 1, NULL, 'Gesamt Liegenschaft'),
(26, 'WP Eingang Stromverbrauch', 'WP_electricity', 'consumption', 1, NULL, ''),
(27, 'WP Ausgang Heizung', 'WP_heat', 'consumption', 1, NULL, ''),
(28, 'WP Ausgang Warmwasser', 'WP_warmwater', 'consumption', 1, NULL, '');

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `zaehlerstaende`
--

CREATE TABLE `zaehlerstaende` (
  `id` int(11) NOT NULL,
  `zaehler_id` int(11) NOT NULL,
  `ablesedatum` date NOT NULL,
  `period` enum('month','year') DEFAULT NULL,
  `value` decimal(10,3) NOT NULL,
  `note` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Daten für Tabelle `zaehlerstaende`
--

INSERT INTO `zaehlerstaende` (`id`, `zaehler_id`, `ablesedatum`, `period`, `value`, `note`) VALUES
(1, 1, '2024-06-30', NULL, 2.370, ''),
(2, 1, '2024-12-31', NULL, 10.391, ''),
(3, 2, '2024-06-30', NULL, 0.996, ''),
(4, 2, '2024-12-31', NULL, 3.183, ''),
(5, 15, '2024-06-30', NULL, 772.200, ''),
(6, 15, '2024-12-31', NULL, 1933.900, ''),
(7, 16, '2024-06-30', NULL, 2.500, ''),
(8, 16, '2024-12-31', NULL, 165.000, ''),
(9, 3, '2024-06-30', NULL, 1.073, ''),
(10, 3, '2024-12-31', NULL, 50.901, ''),
(11, 4, '2024-06-30', NULL, 0.397, ''),
(12, 4, '2024-12-31', NULL, 38.109, ''),
(13, 17, '2024-06-30', NULL, 916.700, ''),
(14, 17, '2024-12-31', NULL, 2139.000, ''),
(15, 18, '2024-06-30', NULL, 24.000, ''),
(16, 18, '2024-12-31', NULL, 238.900, ''),
(17, 5, '2024-06-30', NULL, 3.016, ''),
(18, 5, '2024-12-31', NULL, 31.900, ''),
(19, 6, '2024-06-30', NULL, 0.771, ''),
(20, 6, '2024-12-31', NULL, 6.820, ''),
(21, 19, '2024-06-30', NULL, 273.900, ''),
(22, 19, '2024-12-31', NULL, 1408.400, ''),
(23, 20, '2024-06-30', NULL, 8.000, ''),
(24, 20, '2024-12-31', NULL, 236.900, ''),
(25, 8, '2024-06-30', NULL, 0.270, ''),
(26, 8, '2024-12-31', NULL, 7.872, ''),
(27, 7, '2024-06-30', NULL, 0.379, ''),
(28, 7, '2024-12-31', NULL, 16.784, ''),
(29, 21, '2024-06-30', NULL, 236.400, ''),
(30, 21, '2024-12-31', NULL, 1333.000, ''),
(31, 22, '2024-06-30', NULL, 1.800, ''),
(32, 22, '2024-12-31', NULL, 192.800, ''),
(33, 13, '2024-06-30', NULL, 9722.780, ''),
(34, 13, '2024-12-31', NULL, 11905.704, ''),
(35, 23, '2024-06-30', NULL, 93.369, ''),
(36, 23, '2024-12-31', NULL, 256.685, ''),
(38, 23, '2025-07-01', NULL, 419.021, ''),
(39, 26, '2024-01-01', 'year', 1509.100, 'Ablesung am Gerät pro Jahr'),
(40, 27, '2025-12-31', 'year', 10359.500, ''),
(41, 28, '2024-12-31', 'year', 401.420, NULL),
(42, 13, '2025-08-13', 'month', 14076.000, 'Zwischenablesung'),
(43, 23, '2025-08-13', 'month', 459.531, 'Zwischenablesung'),
(44, 2, '2025-08-13', 'month', 6.285, 'Zwischenablesung'),
(45, 1, '2025-08-13', 'month', 21.533, 'Zwischenablesung'),
(46, 15, '2025-08-13', 'month', 3945.800, 'Zwischenablesung'),
(47, 16, '2025-08-13', 'month', 262.100, 'Zwischenablesung'),
(48, 3, '2025-08-13', 'month', 108.445, 'Zwischenablesung'),
(49, 4, '2025-08-13', 'month', 89.510, 'Zwischenablesung'),
(50, 17, '2025-08-13', 'month', 3398.000, 'Zwischenablesung'),
(51, 18, '2025-08-13', 'month', 414.000, 'Zwischenablesung'),
(52, 6, '2025-08-13', 'month', 17.359, 'Zwischenablesung'),
(53, 5, '2025-08-13', 'month', 64.800, 'Zwischenablesung'),
(54, 19, '2025-08-13', 'month', 2770.800, 'Zwischenablesung'),
(55, 20, '2025-08-13', 'month', 361.300, 'Zwischenablesung'),
(56, 8, '2025-08-13', 'month', 16.890, 'Zwischenablesung'),
(57, 7, '2025-08-13', 'month', 36.277, 'Zwischenablesung'),
(58, 21, '2025-08-13', 'month', 2874.200, 'Zwischenablesung'),
(59, 22, '2025-08-13', 'month', 340.400, 'Zwischenablesung'),
(60, 26, '2025-12-31', 'year', 3916.700, 'Zwischenablesung'),
(61, 27, '2024-01-01', 'year', 1107.679, 'Jahresablesung'),
(62, 28, '2025-12-31', 'year', 8368.700, 'Jahresablesung'),
(63, 23, '2025-12-31', 'month', 603.950, 'Jahresablesung'),
(64, 1, '2025-12-31', 'month', 28.538, 'Jahresablesung'),
(65, 2, '2025-12-31', 'month', 7.544, 'Jahresablesung'),
(66, 3, '2025-12-31', 'month', 151.738, 'Jahresablesung'),
(67, 4, '2025-12-31', 'month', 129.015, 'Jahresablesung'),
(68, 5, '2025-12-31', 'month', 86.595, 'Jahresablesung'),
(69, 6, '2025-12-31', 'month', 24.799, 'Jahresablesung'),
(70, 7, '2025-12-31', 'month', 49.061, 'Jahresablesung'),
(71, 8, '2025-12-31', 'month', 22.661, 'Jahresablesung'),
(72, 13, '2025-12-31', 'month', 15866.790, 'Jahresablesung'),
(74, 15, '2025-12-31', 'month', 5237.900, 'Jahresablesung'),
(75, 16, '2025-12-31', 'month', 270.200, 'Jahresablesung'),
(76, 17, '2025-12-31', 'month', 4718.200, 'Jahresablesung'),
(77, 18, '2025-12-31', 'month', 438.300, 'Jahresablesung'),
(78, 19, '2025-12-31', 'month', 3935.100, 'Jahresablesung'),
(79, 20, '2025-12-31', 'month', 374.600, 'Jahresablesung'),
(80, 21, '2025-12-31', 'month', 3792.400, 'Jahresablesung'),
(81, 22, '2025-12-31', 'month', 357.700, 'Jahresablesung');

-- --------------------------------------------------------

--
-- Stellvertreter-Struktur des Views `zaehler_yearly_consumption`
-- (Siehe unten für die tatsächliche Ansicht)
--
CREATE TABLE `zaehler_yearly_consumption` (
`zaehler_id` int(11)
,`calc_year` int(5)
,`kind` enum('reading','consumption')
,`start_date` date
,`start_value` decimal(10,3)
,`end_date` date
,`end_value` decimal(32,3)
,`duration_days` int(9)
,`avg_per_day` decimal(37,7)
,`consumption` decimal(33,3)
);

-- --------------------------------------------------------

--
-- Struktur des Views `view_allgemeinstrom_abrechnung`
--
DROP TABLE IF EXISTS `view_allgemeinstrom_abrechnung`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_allgemeinstrom_abrechnung`  AS WITH MainMeter AS (SELECT `z`.`liegenschaft_id` AS `liegenschaft_id`, `zyc`.`calc_year` AS `jahr`, coalesce(sum(`zyc`.`consumption`),0) AS `total_kwh` FROM (`zaehler_yearly_consumption` `zyc` join `zaehler` `z` on(`z`.`id` = `zyc`.`zaehler_id`)) WHERE `z`.`zaehlertyp` = 'electricity' AND `z`.`einheit_id` is null GROUP BY `z`.`liegenschaft_id`, `zyc`.`calc_year`), WpElectricity AS (SELECT `z`.`liegenschaft_id` AS `liegenschaft_id`, `zyc`.`calc_year` AS `jahr`, coalesce(sum(`zyc`.`consumption`),0) AS `wp_kwh` FROM (`zaehler_yearly_consumption` `zyc` join `zaehler` `z` on(`z`.`id` = `zyc`.`zaehler_id`)) WHERE `z`.`zaehlertyp` = 'WP_electricity' GROUP BY `z`.`liegenschaft_id`, `zyc`.`calc_year`), StromCosts AS (SELECT `b`.`liegenschaft_id` AS `liegenschaft_id`, year(`b`.`datum`) AS `jahr`, coalesce(sum(`b`.`nettobetrag`),0) AS `total_cost` FROM `buchungen` AS `b` WHERE `b`.`bk` = 'strom' AND `b`.`ausgabe` = 1 AND `b`.`einheit_id` is null GROUP BY `b`.`liegenschaft_id`, year(`b`.`datum`)), BaseUnits AS (SELECT `vb`.`liegenschaft_id` AS `liegenschaft_id`, `vb`.`jahr` AS `jahr`, `vb`.`einheit_id` AS `einheit_id`, `vb`.`einheit_name` AS `einheit_name`, `vb`.`mieter_namen` AS `mieter_namen`, `vb`.`anteil_prozent` AS `anteil_prozent` FROM `view_bk_verteilung` AS `vb`)  SELECT `bu`.`liegenschaft_id` AS `liegenschaft_id`, `bu`.`jahr` AS `jahr`, `bu`.`einheit_id` AS `einheit_id`, `bu`.`einheit_name` AS `einheit_name`, `bu`.`mieter_namen` AS `mieter_namen`, `bu`.`anteil_prozent` AS `anteil_prozent`, coalesce(`mm`.`total_kwh`,0) AS `total_kwh`, coalesce(`wp`.`wp_kwh`,0) AS `wp_kwh`, coalesce(`mm`.`total_kwh`,0) - coalesce(`wp`.`wp_kwh`,0) AS `general_kwh`, CASE WHEN coalesce(`mm`.`total_kwh`,0) > 0 THEN coalesce(`sc`.`total_cost`,0) / `mm`.`total_kwh` ELSE 0 END AS `price_per_kwh`, (coalesce(`mm`.`total_kwh`,0) - coalesce(`wp`.`wp_kwh`,0)) * CASE WHEN coalesce(`mm`.`total_kwh`,0) > 0 THEN coalesce(`sc`.`total_cost`,0) / `mm`.`total_kwh` ELSE 0 END AS `cost_general`, (coalesce(`mm`.`total_kwh`,0) - coalesce(`wp`.`wp_kwh`,0)) * CASE WHEN coalesce(`mm`.`total_kwh`,0) > 0 THEN coalesce(`sc`.`total_cost`,0) / `mm`.`total_kwh` ELSE 0 END* (coalesce(`bu`.`anteil_prozent`,0) / 100) AS `kosten_anteil` FROM (((`BaseUnits` `bu` left join `MainMeter` `mm` on(`mm`.`liegenschaft_id` = `bu`.`liegenschaft_id` and `mm`.`jahr` = `bu`.`jahr`)) left join `WpElectricity` `wp` on(`wp`.`liegenschaft_id` = `bu`.`liegenschaft_id` and `wp`.`jahr` = `bu`.`jahr`)) left join `StromCosts` `sc` on(`sc`.`liegenschaft_id` = `bu`.`liegenschaft_id` and `sc`.`jahr` = `bu`.`jahr`)))  ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_bk_verteilung`
--
DROP TABLE IF EXISTS `view_bk_verteilung`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_bk_verteilung`  AS WITH TotalCosts AS (SELECT `b`.`liegenschaft_id` AS `liegenschaft_id`, year(`b`.`datum`) AS `jahr`, coalesce(sum(`b`.`nettobetrag`),0.00) AS `total_costs` FROM `buchungen` AS `b` WHERE `b`.`bk` = 'bk' AND `b`.`ausgabe` = 1 GROUP BY `b`.`liegenschaft_id`, year(`b`.`datum`)), TotalShares AS (SELECT `e`.`liegenschaft_id` AS `liegenschaft_id`, coalesce(sum(`e`.`bkanteil`),0.00) AS `total_bkanteil` FROM `einheiten` AS `e` WHERE `e`.`typ` = 'Wohnung' GROUP BY `e`.`liegenschaft_id`), Years AS (SELECT DISTINCT `b`.`liegenschaft_id` AS `liegenschaft_id`, year(`b`.`datum`) AS `jahr` FROM `buchungen` AS `b` WHERE `b`.`bk` = 'bk' AND `b`.`ausgabe` = 1), UnitData AS (SELECT `y`.`liegenschaft_id` AS `liegenschaft_id`, `y`.`jahr` AS `jahr`, `e`.`id` AS `einheit_id`, `e`.`name` AS `einheit_name`, `e`.`bkanteil` AS `einheit_bkanteil`, group_concat(distinct concat_ws(' ',`m`.`vorname`,`m`.`nachname`) separator ', ') AS `mieter_namen` FROM (((`Years` `y` join `einheiten` `e` on(`e`.`liegenschaft_id` = `y`.`liegenschaft_id` and `e`.`typ` = 'Wohnung')) left join `mietervertrag` `mv` on(`mv`.`einheit_id` = `e`.`id` and `mv`.`einzugsdatum` <= str_to_date(concat(`y`.`jahr`,'-12-31'),'%Y-%m-%d') and (`mv`.`auszugsdatum` is null or `mv`.`auszugsdatum` >= str_to_date(concat(`y`.`jahr`,'-01-01'),'%Y-%m-%d')))) left join `mieter` `m` on(`m`.`id` = `mv`.`mieter_id` or `m`.`id` = `mv`.`mieter2_id`)) GROUP BY `y`.`liegenschaft_id`, `y`.`jahr`, `e`.`id`, `e`.`name`, `e`.`bkanteil`)  SELECT `ud`.`liegenschaft_id` AS `liegenschaft_id`, `ud`.`jahr` AS `jahr`, `ud`.`einheit_id` AS `einheit_id`, `ud`.`einheit_name` AS `einheit_name`, `ud`.`mieter_namen` AS `mieter_namen`, `ud`.`einheit_bkanteil` AS `einheit_bkanteil`, CASE WHEN `ts`.`total_bkanteil` > 0 THEN coalesce(`ud`.`einheit_bkanteil`,0) / `ts`.`total_bkanteil` * 100 ELSE 0 END AS `anteil_prozent`, round(case when `ts`.`total_bkanteil` > 0 then coalesce(`ud`.`einheit_bkanteil`,0) / `ts`.`total_bkanteil` * `tc`.`total_costs` else 0 end,2) AS `anteil_euro` FROM ((`UnitData` `ud` join `TotalCosts` `tc` on(`tc`.`liegenschaft_id` = `ud`.`liegenschaft_id` and `tc`.`jahr` = `ud`.`jahr`)) left join `TotalShares` `ts` on(`ts`.`liegenschaft_id` = `ud`.`liegenschaft_id`)))  ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_gesamtabrechnung`
--
DROP TABLE IF EXISTS `view_gesamtabrechnung`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_gesamtabrechnung`  AS WITH UnitPayments AS (SELECT `buchungen`.`einheit_id` AS `einheit_id`, year(`buchungen`.`datum`) AS `jahr`, sum(case when `buchungen`.`bk` = 'bk' then `buchungen`.`bruttobetrag` else 0 end) AS `akonto_10`, sum(case when `buchungen`.`bk` = 'heizung' then `buchungen`.`bruttobetrag` else 0 end) AS `akonto_20` FROM `buchungen` WHERE `buchungen`.`ausgabe` = 0 AND `buchungen`.`bk` in ('bk','heizung') AND `buchungen`.`einheit_id` is not null GROUP BY `buchungen`.`einheit_id`, year(`buchungen`.`datum`)), UnitCosts AS (SELECT `vb`.`liegenschaft_id` AS `liegenschaft_id`, `vb`.`jahr` AS `jahr`, `vb`.`einheit_id` AS `einheit_id`, `vb`.`einheit_name` AS `einheit_name`, `vb`.`mieter_namen` AS `mieter_namen`, coalesce(`vw`.`kosten_anteil`,0) AS `cost_wasser`, coalesce(`va`.`kosten_anteil`,0) AS `cost_strom_allg`, coalesce(`vww`.`kosten_netto`,0) AS `cost_ww`, coalesce(`vh`.`kosten_gesamt_netto`,0) AS `cost_heizung` FROM ((((`view_bk_verteilung` `vb` left join `view_wasser_abrechnung` `vw` on(`vw`.`einheit_id` = `vb`.`einheit_id` and `vw`.`jahr` = `vb`.`jahr`)) left join `view_allgemeinstrom_abrechnung` `va` on(`va`.`einheit_id` = `vb`.`einheit_id` and `va`.`jahr` = `vb`.`jahr`)) left join `view_warmwasser_abrechnung` `vww` on(`vww`.`einheit_id` = `vb`.`einheit_id` and `vww`.`jahr` = `vb`.`jahr`)) left join `view_heizung_abrechnung` `vh` on(`vh`.`einheit_id` = `vb`.`einheit_id` and `vh`.`jahr` = `vb`.`jahr`)))  SELECT `uc`.`liegenschaft_id` AS `liegenschaft_id`, `uc`.`jahr` AS `jahr`, `uc`.`einheit_id` AS `einheit_id`, `uc`.`einheit_name` AS `einheit_name`, `uc`.`mieter_namen` AS `mieter_namen`, `uc`.`cost_wasser` AS `cost_wasser`, `uc`.`cost_strom_allg` AS `cost_strom_allg`, `uc`.`cost_ww` AS `cost_ww`, `uc`.`cost_heizung` AS `cost_heizung`, `uc`.`cost_wasser`+ `uc`.`cost_strom_allg` + `uc`.`cost_ww` AS `netto_10`, (`uc`.`cost_wasser` + `uc`.`cost_strom_allg` + `uc`.`cost_ww`) * 0.10 AS `ust_10`, `uc`.`cost_heizung` AS `netto_20`, `uc`.`cost_heizung`* 0.20 AS `ust_20`, coalesce(`up`.`akonto_10`,0) AS `akonto_10`, coalesce(`up`.`akonto_20`,0) AS `akonto_20`, (`uc`.`cost_wasser` + `uc`.`cost_strom_allg` + `uc`.`cost_ww`) * 1.10 + `uc`.`cost_heizung` * 1.20 AS `total_brutto`, coalesce(`up`.`akonto_10`,0) + coalesce(`up`.`akonto_20`,0) AS `total_akonto`, coalesce(`up`.`akonto_10`,0) + coalesce(`up`.`akonto_20`,0) - ((`uc`.`cost_wasser` + `uc`.`cost_strom_allg` + `uc`.`cost_ww`) * 1.10 + `uc`.`cost_heizung` * 1.20) AS `saldo` FROM (`UnitCosts` `uc` left join `UnitPayments` `up` on(`up`.`einheit_id` = `uc`.`einheit_id` and `up`.`jahr` = `uc`.`jahr`)))  ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_gesamtabrechnung_detail`
--
DROP TABLE IF EXISTS `view_gesamtabrechnung_detail`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_gesamtabrechnung_detail`  AS WITH UnitPayments AS (SELECT `buchungen`.`einheit_id` AS `einheit_id`, year(`buchungen`.`datum`) AS `jahr`, sum(case when `buchungen`.`bk` = 'bk' then `buchungen`.`bruttobetrag` else 0 end) AS `akonto_10_brutto`, sum(case when `buchungen`.`bk` = 'heizung' then `buchungen`.`bruttobetrag` else 0 end) AS `akonto_20_brutto` FROM `buchungen` WHERE `buchungen`.`ausgabe` = 0 AND `buchungen`.`einheit_id` is not null GROUP BY `buchungen`.`einheit_id`, year(`buchungen`.`datum`)), AllCosts AS (SELECT `vb`.`liegenschaft_id` AS `liegenschaft_id`, `vb`.`jahr` AS `jahr`, `vb`.`einheit_id` AS `einheit_id`, `vb`.`einheit_name` AS `einheit_name`, `vb`.`mieter_namen` AS `mieter_namen`, coalesce(`vb`.`anteil_euro`,0) AS `cost_bk_basis`, coalesce(`vw`.`kosten_anteil`,0) AS `cost_wasser`, coalesce(`va`.`kosten_anteil`,0) AS `cost_strom_allg`, coalesce(`vww`.`kosten_netto`,0) AS `cost_ww`, coalesce(`vh`.`kosten_gesamt_netto`,0) AS `cost_heizung`, coalesce(`vb`.`anteil_euro`,0) + coalesce(`vw`.`kosten_anteil`,0) + coalesce(`va`.`kosten_anteil`,0) + coalesce(`vww`.`kosten_netto`,0) AS `netto_10_total`, coalesce(`vh`.`kosten_gesamt_netto`,0) AS `netto_20_total` FROM ((((`view_bk_verteilung` `vb` left join `view_wasser_abrechnung` `vw` on(`vw`.`einheit_id` = `vb`.`einheit_id` and `vw`.`jahr` = `vb`.`jahr`)) left join `view_allgemeinstrom_abrechnung` `va` on(`va`.`einheit_id` = `vb`.`einheit_id` and `va`.`jahr` = `vb`.`jahr`)) left join `view_warmwasser_abrechnung` `vww` on(`vww`.`einheit_id` = `vb`.`einheit_id` and `vww`.`jahr` = `vb`.`jahr`)) left join `view_heizung_abrechnung` `vh` on(`vh`.`einheit_id` = `vb`.`einheit_id` and `vh`.`jahr` = `vb`.`jahr`)))  SELECT `ac`.`liegenschaft_id` AS `liegenschaft_id`, `ac`.`jahr` AS `jahr`, `ac`.`einheit_id` AS `einheit_id`, `ac`.`einheit_name` AS `einheit_name`, `ac`.`mieter_namen` AS `mieter_namen`, `ac`.`cost_strom_allg` AS `cost_strom_allg`, `ac`.`cost_ww` AS `cost_ww`, `ac`.`cost_heizung` AS `cost_heizung`, `ac`.`netto_10_total` AS `netto_10_total`, `ac`.`netto_10_total`* 0.10 AS `ust_10_total`, `ac`.`netto_10_total`* 1.10 AS `brutto_10_total`, coalesce(`up`.`akonto_10_brutto`,0) AS `akonto_10_brutto`, coalesce(`up`.`akonto_10_brutto`,0) - `ac`.`netto_10_total` * 1.10 AS `saldo_10`, `ac`.`netto_20_total` AS `netto_20_total`, `ac`.`netto_20_total`* 0.20 AS `ust_20_total`, `ac`.`netto_20_total`* 1.20 AS `brutto_20_total`, coalesce(`up`.`akonto_20_brutto`,0) AS `akonto_20_brutto`, coalesce(`up`.`akonto_20_brutto`,0) - `ac`.`netto_20_total` * 1.20 AS `saldo_20`, `ac`.`netto_10_total`+ `ac`.`netto_20_total` AS `total_netto_costs`, `ac`.`netto_10_total`* 1.10 + `ac`.`netto_20_total` * 1.20 AS `total_brutto_costs`, coalesce(`up`.`akonto_10_brutto`,0) + coalesce(`up`.`akonto_20_brutto`,0) - (`ac`.`netto_10_total` * 1.10 + `ac`.`netto_20_total` * 1.20) AS `total_saldo` FROM (`AllCosts` `ac` left join `UnitPayments` `up` on(`up`.`einheit_id` = `ac`.`einheit_id` and `up`.`jahr` = `ac`.`jahr`)))  ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_heizung_abrechnung`
--
DROP TABLE IF EXISTS `view_heizung_abrechnung`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_heizung_abrechnung`  AS WITH UnitMeasured AS (SELECT `z`.`einheit_id` AS `einheit_id`, `zyc`.`calc_year` AS `jahr`, coalesce(sum(`zyc`.`consumption`),0) AS `verbrauch_kwh` FROM (`zaehler_yearly_consumption` `zyc` join `zaehler` `z` on(`z`.`id` = `zyc`.`zaehler_id`)) WHERE `z`.`einheit_id` is not null AND `z`.`zaehlertyp` = 'heat_energy' GROUP BY `z`.`einheit_id`, `zyc`.`calc_year`), GlobalParams AS (SELECT DISTINCT `va`.`liegenschaft_id` AS `liegenschaft_id`, `va`.`jahr` AS `jahr`, coalesce(`va`.`price_per_kwh`,0) AS `price_per_kwh`, coalesce(`wpm`.`input_kwh`,0) AS `input_kwh`, coalesce(`wpm`.`ratio_heat`,0) AS `ratio_heat`, `l`.`heat_usage_percent` AS `percent_config` FROM ((`view_allgemeinstrom_abrechnung` `va` join `view_wp_metrics` `wpm` on(`wpm`.`liegenschaft_id` = `va`.`liegenschaft_id` and `wpm`.`jahr` = `va`.`jahr`)) join `liegenschaften` `l` on(`l`.`id` = `va`.`liegenschaft_id`))), PoolCalculation AS (SELECT `GlobalParams`.`liegenschaft_id` AS `liegenschaft_id`, `GlobalParams`.`jahr` AS `jahr`, `GlobalParams`.`input_kwh`* `GlobalParams`.`price_per_kwh` * `GlobalParams`.`ratio_heat` AS `total_heizung_euro`, `GlobalParams`.`percent_config` AS `percent_config`, `GlobalParams`.`input_kwh`* `GlobalParams`.`price_per_kwh` * `GlobalParams`.`ratio_heat` * (`GlobalParams`.`percent_config` / 100.0) AS `pool_fix_euro`, `GlobalParams`.`input_kwh`* `GlobalParams`.`price_per_kwh` * `GlobalParams`.`ratio_heat` * (1 - `GlobalParams`.`percent_config` / 100.0) AS `pool_var_euro` FROM `GlobalParams`), HouseTotals AS (SELECT `um`.`jahr` AS `jahr`, `z`.`liegenschaft_id` AS `liegenschaft_id`, sum(`um`.`verbrauch_kwh`) AS `total_haus_kwh` FROM (`UnitMeasured` `um` join `zaehler` `z` on(`z`.`einheit_id` = `um`.`einheit_id`)) WHERE `z`.`zaehlertyp` = 'heat_energy' GROUP BY `um`.`jahr`, `z`.`liegenschaft_id`)  SELECT `bu`.`liegenschaft_id` AS `liegenschaft_id`, `bu`.`jahr` AS `jahr`, `bu`.`einheit_id` AS `einheit_id`, `bu`.`einheit_name` AS `einheit_name`, `bu`.`mieter_namen` AS `mieter_namen`, coalesce(`um`.`verbrauch_kwh`,0) AS `measured_kwh`, `pc`.`total_heizung_euro` AS `total_heizung_euro`, `pc`.`percent_config` AS `percent_config`, `pc`.`pool_fix_euro`* (coalesce(`bu`.`anteil_prozent`,0) / 100) AS `kosten_fix`, CASE WHEN `ht`.`total_haus_kwh` > 0 THEN coalesce(`um`.`verbrauch_kwh`,0) * (`pc`.`pool_var_euro` / `ht`.`total_haus_kwh`) ELSE 0 END AS `kosten_var`, CASE WHEN `ht`.`total_haus_kwh` > 0 THEN `pc`.`pool_var_euro`/ `ht`.`total_haus_kwh` ELSE 0 END AS `preis_pro_kwh`, `pc`.`pool_fix_euro`* (coalesce(`bu`.`anteil_prozent`,0) / 100) + CASE WHEN `ht`.`total_haus_kwh` > 0 THEN coalesce(`um`.`verbrauch_kwh`,0) * (`pc`.`pool_var_euro` / `ht`.`total_haus_kwh`) ELSE 0 END AS `kosten_gesamt_netto` FROM (((`view_bk_verteilung` `bu` left join `UnitMeasured` `um` on(`um`.`einheit_id` = `bu`.`einheit_id` and `um`.`jahr` = `bu`.`jahr`)) left join `PoolCalculation` `pc` on(`pc`.`liegenschaft_id` = `bu`.`liegenschaft_id` and `pc`.`jahr` = `bu`.`jahr`)) left join `HouseTotals` `ht` on(`ht`.`liegenschaft_id` = `bu`.`liegenschaft_id` and `ht`.`jahr` = `bu`.`jahr`)))  ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_mieter_saldo`
--
DROP TABLE IF EXISTS `view_mieter_saldo`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_mieter_saldo`  AS SELECT `j`.`mieter_id` AS `mieter_id`, coalesce(sum(`j`.`betrag`),0.00) AS `saldo` FROM `journal` AS `j` WHERE `j`.`mieter_id` is not null AND `j`.`kategorie` in ('FORDERUNG','ZAHLUNG') GROUP BY `j`.`mieter_id` ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_objekt_uebersicht`
--
DROP TABLE IF EXISTS `view_objekt_uebersicht`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_objekt_uebersicht`  AS SELECT `b`.`liegenschaft_id` AS `liegenschaft_id`, year(`b`.`datum`) AS `jahr`, coalesce(sum(case when `b`.`ausgabe` = 1 and `b`.`bk` = 'bk' then `b`.`nettobetrag` else 0 end),0.00) AS `kosten_bk_netto`, coalesce(sum(case when `b`.`ausgabe` = 1 and `b`.`bk` = 'strom' then `b`.`nettobetrag` else 0 end),0.00) AS `kosten_strom_netto`, coalesce(sum(case when `b`.`ausgabe` = 1 and `b`.`bk` = 'wasser' then `b`.`nettobetrag` else 0 end),0.00) AS `kosten_wasser_netto`, coalesce(sum(case when `b`.`ausgabe` = 0 and `b`.`bk` = 'bk' then `b`.`nettobetrag` else 0 end),0.00) AS `einnahmen_bk_netto`, coalesce(sum(case when `b`.`ausgabe` = 0 and `b`.`bk` = 'heizung' then `b`.`nettobetrag` else 0 end),0.00) AS `einnahmen_heizung_netto` FROM `buchungen` AS `b` GROUP BY `b`.`liegenschaft_id`, year(`b`.`datum`) ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_warmwasser_abrechnung`
--
DROP TABLE IF EXISTS `view_warmwasser_abrechnung`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_warmwasser_abrechnung`  AS WITH UnitMeasured AS (SELECT `z`.`einheit_id` AS `einheit_id`, `zyc`.`calc_year` AS `jahr`, coalesce(sum(`zyc`.`consumption`),0) AS `verbrauch` FROM (`zaehler_yearly_consumption` `zyc` join `zaehler` `z` on(`z`.`id` = `zyc`.`zaehler_id`)) WHERE `z`.`einheit_id` is not null AND `z`.`zaehlertyp` = 'water_hot' GROUP BY `z`.`einheit_id`, `zyc`.`calc_year`), BaseUnits AS (SELECT DISTINCT `view_bk_verteilung`.`liegenschaft_id` AS `liegenschaft_id`, `view_bk_verteilung`.`jahr` AS `jahr`, `view_bk_verteilung`.`einheit_id` AS `einheit_id`, `view_bk_verteilung`.`einheit_name` AS `einheit_name`, `view_bk_verteilung`.`mieter_namen` AS `mieter_namen` FROM `view_bk_verteilung`), GlobalParams AS (SELECT DISTINCT `va`.`liegenschaft_id` AS `liegenschaft_id`, `va`.`jahr` AS `jahr`, `va`.`price_per_kwh` AS `price_per_kwh`, `wpm`.`input_kwh` AS `input_kwh`, `wpm`.`ratio_ww` AS `ratio_ww`, `wpm`.`jaz` AS `jaz` FROM (`view_allgemeinstrom_abrechnung` `va` join `view_wp_metrics` `wpm` on(`wpm`.`liegenschaft_id` = `va`.`liegenschaft_id` and `wpm`.`jahr` = `va`.`jahr`))), HouseTotals AS (SELECT `um`.`jahr` AS `jahr`, `z`.`liegenschaft_id` AS `liegenschaft_id`, sum(`um`.`verbrauch`) AS `total_m3_haus` FROM (`UnitMeasured` `um` join `zaehler` `z` on(`z`.`einheit_id` = `um`.`einheit_id`)) WHERE `z`.`zaehlertyp` = 'water_hot' GROUP BY `um`.`jahr`, `z`.`liegenschaft_id`)  SELECT `bu`.`liegenschaft_id` AS `liegenschaft_id`, `bu`.`jahr` AS `jahr`, `bu`.`einheit_id` AS `einheit_id`, `bu`.`einheit_name` AS `einheit_name`, `bu`.`mieter_namen` AS `mieter_namen`, coalesce(`um`.`verbrauch`,0) AS `measured_m3`, coalesce(`gp`.`input_kwh` * `gp`.`price_per_kwh`,0) AS `kosten_wp_gesamt`, coalesce(`gp`.`input_kwh` * `gp`.`price_per_kwh` * `gp`.`ratio_ww`,0) AS `kosten_pool_ww`, `gp`.`jaz` AS `jaz`, `gp`.`ratio_ww` AS `ratio_ww`, CASE WHEN `ht`.`total_m3_haus` > 0 THEN `gp`.`input_kwh`* `gp`.`price_per_kwh` * `gp`.`ratio_ww` / `ht`.`total_m3_haus` ELSE 0 END AS `price_per_m3`, CASE WHEN `ht`.`total_m3_haus` > 0 THEN `um`.`verbrauch`* (`gp`.`input_kwh` * `gp`.`price_per_kwh` * `gp`.`ratio_ww` / `ht`.`total_m3_haus`) ELSE 0 END AS `kosten_netto` FROM (((`BaseUnits` `bu` left join `UnitMeasured` `um` on(`um`.`einheit_id` = `bu`.`einheit_id` and `um`.`jahr` = `bu`.`jahr`)) left join `GlobalParams` `gp` on(`gp`.`liegenschaft_id` = `bu`.`liegenschaft_id` and `gp`.`jahr` = `bu`.`jahr`)) left join `HouseTotals` `ht` on(`ht`.`liegenschaft_id` = `bu`.`liegenschaft_id` and `ht`.`jahr` = `bu`.`jahr`)))  ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_wasser_abrechnung`
--
DROP TABLE IF EXISTS `view_wasser_abrechnung`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_wasser_abrechnung`  AS WITH Financials AS (SELECT `vo`.`liegenschaft_id` AS `liegenschaft_id`, `vo`.`jahr` AS `jahr`, `vo`.`kosten_wasser_netto` AS `kosten_wasser_netto` FROM `view_objekt_uebersicht` AS `vo`), MainMeter AS (SELECT `z`.`liegenschaft_id` AS `liegenschaft_id`, `zyc`.`calc_year` AS `jahr`, coalesce(sum(`zyc`.`consumption`),0) AS `gesamt_m3_hauptzaehler` FROM (`zaehler_yearly_consumption` `zyc` join `zaehler` `z` on(`z`.`id` = `zyc`.`zaehler_id`)) WHERE `z`.`einheit_id` is null AND `z`.`zaehlertyp` = 'water_cold' GROUP BY `z`.`liegenschaft_id`, `zyc`.`calc_year`), UnitMeasured AS (SELECT `z`.`liegenschaft_id` AS `liegenschaft_id`, `zyc`.`calc_year` AS `jahr`, `z`.`einheit_id` AS `einheit_id`, coalesce(sum(`zyc`.`consumption`),0) AS `verbrauch_gemessen` FROM (`zaehler_yearly_consumption` `zyc` join `zaehler` `z` on(`z`.`id` = `zyc`.`zaehler_id`)) WHERE `z`.`einheit_id` is not null AND `z`.`zaehlertyp` in ('water_cold','water_hot') GROUP BY `z`.`liegenschaft_id`, `zyc`.`calc_year`, `z`.`einheit_id`), UnitTotals AS (SELECT `um`.`liegenschaft_id` AS `liegenschaft_id`, `um`.`jahr` AS `jahr`, coalesce(sum(`um`.`verbrauch_gemessen`),0) AS `gesamt_m3_wohnungen` FROM `UnitMeasured` AS `um` GROUP BY `um`.`liegenschaft_id`, `um`.`jahr`), VerteilungKeys AS (SELECT `vb`.`liegenschaft_id` AS `liegenschaft_id`, `vb`.`jahr` AS `jahr`, `vb`.`einheit_id` AS `einheit_id`, `vb`.`einheit_name` AS `einheit_name`, `vb`.`mieter_namen` AS `mieter_namen`, `vb`.`anteil_prozent` AS `anteil_prozent` FROM `view_bk_verteilung` AS `vb`), Globals AS (SELECT `k`.`liegenschaft_id` AS `liegenschaft_id`, `k`.`jahr` AS `jahr`, coalesce(`mm`.`gesamt_m3_hauptzaehler`,0) AS `gesamt_m3_hauptzaehler`, coalesce(`ut`.`gesamt_m3_wohnungen`,0) AS `gesamt_m3_wohnungen`, coalesce(`mm`.`gesamt_m3_hauptzaehler`,0) - coalesce(`ut`.`gesamt_m3_wohnungen`,0) AS `schwund_m3`, CASE WHEN coalesce(`mm`.`gesamt_m3_hauptzaehler`,0) > 0 THEN coalesce(`f`.`kosten_wasser_netto`,0) / `mm`.`gesamt_m3_hauptzaehler` ELSE 0 END AS `preis_pro_m3` FROM (((`VerteilungKeys` `k` left join `Financials` `f` on(`f`.`liegenschaft_id` = `k`.`liegenschaft_id` and `f`.`jahr` = `k`.`jahr`)) left join `MainMeter` `mm` on(`mm`.`liegenschaft_id` = `k`.`liegenschaft_id` and `mm`.`jahr` = `k`.`jahr`)) left join `UnitTotals` `ut` on(`ut`.`liegenschaft_id` = `k`.`liegenschaft_id` and `ut`.`jahr` = `k`.`jahr`)) GROUP BY `k`.`liegenschaft_id`, `k`.`jahr`, `mm`.`gesamt_m3_hauptzaehler`, `ut`.`gesamt_m3_wohnungen`, `f`.`kosten_wasser_netto`)  SELECT `k`.`liegenschaft_id` AS `liegenschaft_id`, `k`.`jahr` AS `jahr`, `k`.`einheit_id` AS `einheit_id`, `k`.`einheit_name` AS `einheit_name`, `k`.`mieter_namen` AS `mieter_namen`, coalesce(`um`.`verbrauch_gemessen`,0) AS `verbrauch_gemessen`, coalesce(`g`.`schwund_m3`,0) * (coalesce(`k`.`anteil_prozent`,0) / 100) AS `anteil_schwund`, coalesce(`um`.`verbrauch_gemessen`,0) + coalesce(`g`.`schwund_m3`,0) * (coalesce(`k`.`anteil_prozent`,0) / 100) AS `verbrauch_gesamt`, (coalesce(`um`.`verbrauch_gemessen`,0) + coalesce(`g`.`schwund_m3`,0) * (coalesce(`k`.`anteil_prozent`,0) / 100)) * coalesce(`g`.`preis_pro_m3`,0) AS `kosten_anteil` FROM ((`VerteilungKeys` `k` left join `UnitMeasured` `um` on(`um`.`liegenschaft_id` = `k`.`liegenschaft_id` and `um`.`jahr` = `k`.`jahr` and `um`.`einheit_id` = `k`.`einheit_id`)) left join `Globals` `g` on(`g`.`liegenschaft_id` = `k`.`liegenschaft_id` and `g`.`jahr` = `k`.`jahr`)))  ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_wp_metrics`
--
DROP TABLE IF EXISTS `view_wp_metrics`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_wp_metrics`  AS WITH consumption_rollup AS (SELECT `z`.`liegenschaft_id` AS `liegenschaft_id`, `zyc`.`calc_year` AS `jahr`, coalesce(sum(case when `z`.`zaehlertyp` = 'WP_electricity' then `zyc`.`consumption` else 0 end),0) AS `input_kwh`, coalesce(sum(case when `z`.`zaehlertyp` = 'WP_heat' then `zyc`.`consumption` else 0 end),0) AS `output_heat_kwh`, coalesce(sum(case when `z`.`zaehlertyp` = 'WP_warmwater' then `zyc`.`consumption` else 0 end),0) AS `output_ww_kwh` FROM (`zaehler_yearly_consumption` `zyc` join `zaehler` `z` on(`z`.`id` = `zyc`.`zaehler_id`)) GROUP BY `z`.`liegenschaft_id`, `zyc`.`calc_year`) SELECT `cr`.`liegenschaft_id` AS `liegenschaft_id`, `cr`.`jahr` AS `jahr`, `cr`.`input_kwh` AS `input_kwh`, `cr`.`output_heat_kwh` AS `output_heat_kwh`, `cr`.`output_ww_kwh` AS `output_ww_kwh`, coalesce(`cr`.`output_heat_kwh`,0) + coalesce(`cr`.`output_ww_kwh`,0) AS `total_output_kwh`, (coalesce(`cr`.`output_heat_kwh`,0) + coalesce(`cr`.`output_ww_kwh`,0)) / nullif(coalesce(`cr`.`input_kwh`,0),0) AS `jaz`, coalesce(`cr`.`output_ww_kwh`,0) / nullif(coalesce(`cr`.`output_heat_kwh`,0) + coalesce(`cr`.`output_ww_kwh`,0),0) AS `ratio_ww`, coalesce(`cr`.`output_heat_kwh`,0) / nullif(coalesce(`cr`.`output_heat_kwh`,0) + coalesce(`cr`.`output_ww_kwh`,0),0) AS `ratio_heat` FROM `consumption_rollup` AS `cr``cr`  ;

-- --------------------------------------------------------

--
-- Struktur des Views `view_zaehler_trend_vergleich`
--
DROP TABLE IF EXISTS `view_zaehler_trend_vergleich`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `view_zaehler_trend_vergleich`  AS SELECT `curr`.`zaehler_id` AS `zaehler_id`, `z`.`zaehlernummer` AS `zaehlernummer`, `z`.`zaehlertyp` AS `zaehlertyp`, `z`.`liegenschaft_id` AS `liegenschaft_id`, `z`.`einheit_id` AS `einheit_id`, `e`.`name` AS `einheit_name`, `e`.`top` AS `einheit_top`, `curr`.`calc_year` AS `jahr`, `curr`.`consumption` AS `verbrauch`, `curr`.`avg_per_day` AS `daily_avg`, `curr`.`duration_days` AS `tage`, `prev`.`calc_year` AS `prev_jahr`, `prev`.`consumption` AS `prev_verbrauch`, `prev`.`avg_per_day` AS `prev_daily_avg`, (`curr`.`avg_per_day` / nullif(`prev`.`avg_per_day`,0) - 1) * 100 AS `trend_prozent` FROM (((`zaehler_yearly_consumption` `curr` join `zaehler` `z` on(`curr`.`zaehler_id` = `z`.`id`)) left join `einheiten` `e` on(`z`.`einheit_id` = `e`.`id`)) left join `zaehler_yearly_consumption` `prev` on(`curr`.`zaehler_id` = `prev`.`zaehler_id` and `curr`.`calc_year` = `prev`.`calc_year` + 1)) ;

-- --------------------------------------------------------

--
-- Struktur des Views `zaehler_yearly_consumption`
--
DROP TABLE IF EXISTS `zaehler_yearly_consumption`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `zaehler_yearly_consumption`  AS WITH base_years AS (SELECT `z`.`id` AS `zaehler_id`, `z`.`kind` AS `kind`, year(`zs`.`ablesedatum`) AS `calc_year` FROM (`zaehlerstaende` `zs` join `zaehler` `z` on(`z`.`id` = `zs`.`zaehler_id`)) GROUP BY `z`.`id`, `z`.`kind`, year(`zs`.`ablesedatum`)), consumption_data AS (SELECT `z`.`id` AS `zaehler_id`, year(`zs`.`ablesedatum`) AS `calc_year`, sum(case when `zs`.`period` = 'month' then `zs`.`value` else 0 end) AS `monthly_total`, sum(case when `zs`.`period` = 'month' then 1 else 0 end) AS `monthly_count`, sum(`zs`.`value`) AS `total_value`, min(`zs`.`ablesedatum`) AS `min_date`, max(`zs`.`ablesedatum`) AS `max_date`, count(0) AS `reading_count` FROM (`zaehlerstaende` `zs` join `zaehler` `z` on(`z`.`id` = `zs`.`zaehler_id`)) WHERE `z`.`kind` = 'consumption' GROUP BY `z`.`id`, year(`zs`.`ablesedatum`)), start_readings AS (SELECT `b`.`zaehler_id` AS `zaehler_id`, `b`.`calc_year` AS `calc_year`, coalesce((select `zs`.`ablesedatum` from `zaehlerstaende` `zs` where `zs`.`zaehler_id` = `b`.`zaehler_id` and `zs`.`ablesedatum` <= makedate(`b`.`calc_year`,1) order by `zs`.`ablesedatum` desc,`zs`.`id` desc limit 1),(select `zs`.`ablesedatum` from `zaehlerstaende` `zs` where `zs`.`zaehler_id` = `b`.`zaehler_id` and `zs`.`ablesedatum` between makedate(`b`.`calc_year`,1) and makedate(`b`.`calc_year`,1) + interval 1 year - interval 1 day order by `zs`.`ablesedatum`,`zs`.`id` limit 1)) AS `start_date`, coalesce((select `zs`.`value` from `zaehlerstaende` `zs` where `zs`.`zaehler_id` = `b`.`zaehler_id` and `zs`.`ablesedatum` <= makedate(`b`.`calc_year`,1) order by `zs`.`ablesedatum` desc,`zs`.`id` desc limit 1),(select `zs`.`value` from `zaehlerstaende` `zs` where `zs`.`zaehler_id` = `b`.`zaehler_id` and `zs`.`ablesedatum` between makedate(`b`.`calc_year`,1) and makedate(`b`.`calc_year`,1) + interval 1 year - interval 1 day order by `zs`.`ablesedatum`,`zs`.`id` limit 1)) AS `start_value` FROM `base_years` AS `b` WHERE `b`.`kind` = 'reading'), end_readings AS (SELECT `b`.`zaehler_id` AS `zaehler_id`, `b`.`calc_year` AS `calc_year`, (select `zs`.`ablesedatum` from `zaehlerstaende` `zs` where `zs`.`zaehler_id` = `b`.`zaehler_id` and `zs`.`ablesedatum` <= makedate(`b`.`calc_year`,1) + interval 1 year - interval 1 day order by `zs`.`ablesedatum` desc,`zs`.`id` desc limit 1) AS `end_date`, (select `zs`.`value` from `zaehlerstaende` `zs` where `zs`.`zaehler_id` = `b`.`zaehler_id` and `zs`.`ablesedatum` <= makedate(`b`.`calc_year`,1) + interval 1 year - interval 1 day order by `zs`.`ablesedatum` desc,`zs`.`id` desc limit 1) AS `end_value` FROM `base_years` AS `b` WHERE `b`.`kind` = 'reading'), assembled AS (SELECT `b`.`zaehler_id` AS `zaehler_id`, `b`.`calc_year` AS `calc_year`, `b`.`kind` AS `kind`, CASE WHEN `b`.`kind` = 'consumption' THEN makedate(`b`.`calc_year`,1) ELSE `sr`.`start_date` END AS `start_date_final`, CASE WHEN `b`.`kind` = 'consumption' THEN NULL ELSE `sr`.`start_value` END AS `start_value_final`, CASE WHEN `b`.`kind` = 'consumption' THEN CASE WHEN `cd`.`reading_count` = 1 THEN `cd`.`max_date` ELSE makedate(`b`.`calc_year`,1) + interval 1 year - interval 1 day END ELSE `er`.`end_date` END AS `end_date_final`, CASE WHEN `b`.`kind` = 'consumption' THEN CASE WHEN `cd`.`monthly_count` > 0 THEN `cd`.`monthly_total` ELSE `cd`.`total_value` END ELSE `er`.`end_value` END AS `end_value_final`, CASE WHEN `b`.`kind` = 'consumption' THEN `cd`.`reading_count` ELSE NULL END AS `reading_count` FROM (((`base_years` `b` left join `consumption_data` `cd` on(`cd`.`zaehler_id` = `b`.`zaehler_id` and `cd`.`calc_year` = `b`.`calc_year`)) left join `start_readings` `sr` on(`sr`.`zaehler_id` = `b`.`zaehler_id` and `sr`.`calc_year` = `b`.`calc_year`)) left join `end_readings` `er` on(`er`.`zaehler_id` = `b`.`zaehler_id` and `er`.`calc_year` = `b`.`calc_year`))), finalized AS (SELECT `a`.`zaehler_id` AS `zaehler_id`, `a`.`calc_year` AS `calc_year`, `a`.`kind` AS `kind`, `a`.`start_date_final` AS `start_date_final`, `a`.`start_value_final` AS `start_value_final`, `a`.`end_date_final` AS `end_date_final`, `a`.`end_value_final` AS `end_value_final`, `a`.`reading_count` AS `reading_count`, CASE WHEN `a`.`start_date_final` is not null AND `a`.`end_date_final` is not null THEN to_days(`a`.`end_date_final`) - to_days(`a`.`start_date_final`) + 1 ELSE NULL END AS `duration_days_final` FROM `assembled` AS `a`) SELECT `f`.`zaehler_id` AS `zaehler_id`, `f`.`calc_year` AS `calc_year`, `f`.`kind` AS `kind`, `f`.`start_date_final` AS `start_date`, `f`.`start_value_final` AS `start_value`, `f`.`end_date_final` AS `end_date`, `f`.`end_value_final` AS `end_value`, `f`.`duration_days_final` AS `duration_days`, CASE WHEN `f`.`duration_days_final` is not null AND `f`.`end_value_final` is not null THEN CASE WHEN `f`.`kind` = 'consumption' THEN `f`.`end_value_final`/ `f`.`duration_days_final` WHEN `f`.`start_value_final` is not null THEN (`f`.`end_value_final` - `f`.`start_value_final`) / `f`.`duration_days_final` ELSE NULL END ELSE NULL END AS `avg_per_day`, CASE WHEN `f`.`kind` = 'consumption' THEN `f`.`end_value_final` WHEN `f`.`start_value_final` is not null AND `f`.`end_value_final` is not null THEN `f`.`end_value_final`- `f`.`start_value_final` ELSE NULL END AS `consumption` FROM `finalized` AS `f` WHERE `f`.`end_value_final` is not nullnot null  ;

--
-- Indizes der exportierten Tabellen
--

--
-- Indizes für die Tabelle `auszuege`
--
ALTER TABLE `auszuege`
  ADD PRIMARY KEY (`id`);

--
-- Indizes für die Tabelle `bank_imports`
--
ALTER TABLE `bank_imports`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `trans_hash` (`trans_hash`),
  ADD UNIQUE KEY `unique_trans` (`trans_hash`);

--
-- Indizes für die Tabelle `buchungen`
--
ALTER TABLE `buchungen`
  ADD PRIMARY KEY (`id`),
  ADD KEY `einheit_id` (`einheit_id`),
  ADD KEY `liegenschaft_id` (`liegenschaft_id`) USING BTREE,
  ADD KEY `sachkonto_id` (`sachkonto_id`);

--
-- Indizes für die Tabelle `dateien`
--
ALTER TABLE `dateien`
  ADD PRIMARY KEY (`id`),
  ADD KEY `fk_dateien_einheit` (`einheit_id`),
  ADD KEY `fk_dateien_liegenschaft` (`liegenschaft_id`),
  ADD KEY `fk_dateien_mietvertrag` (`mietvertrag_id`),
  ADD KEY `fk_dateien_mieter` (`mieter_id`),
  ADD KEY `fk_dateien_meter` (`meter_id`),
  ADD KEY `fk_dateien_zaehlerstand` (`zaehlerstand_id`);

--
-- Indizes für die Tabelle `eigentuemer`
--
ALTER TABLE `eigentuemer`
  ADD PRIMARY KEY (`id`);

--
-- Indizes für die Tabelle `einheiten`
--
ALTER TABLE `einheiten`
  ADD PRIMARY KEY (`id`),
  ADD KEY `liegenschaft_id` (`liegenschaft_id`),
  ADD KEY `idx_einheiten_liegenschaft` (`liegenschaft_id`);

--
-- Indizes für die Tabelle `journal`
--
ALTER TABLE `journal`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_journal_mieter_id` (`mieter_id`),
  ADD KEY `idx_journal_uuid` (`uuid`);

--
-- Indizes für die Tabelle `liegenschaften`
--
ALTER TABLE `liegenschaften`
  ADD PRIMARY KEY (`id`),
  ADD KEY `fk_lieg_eigentuemer1` (`eigentuemer1_id`),
  ADD KEY `fk_lieg_eigentuemer2` (`eigentuemer2_id`);

--
-- Indizes für die Tabelle `mieter`
--
ALTER TABLE `mieter`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_mieter_bank_account_id` (`bank_account_id`);

--
-- Indizes für die Tabelle `mietervertrag`
--
ALTER TABLE `mietervertrag`
  ADD PRIMARY KEY (`id`),
  ADD KEY `mieter_id` (`mieter_id`),
  ADD KEY `einheit_id` (`einheit_id`),
  ADD KEY `fk_mietervertrag_mieter2` (`mieter2_id`),
  ADD KEY `idx_mietervertrag_mieter_dates` (`mieter_id`,`mieter2_id`,`einzugsdatum`,`auszugsdatum`),
  ADD KEY `fk_mietervertrag_verwalter` (`verwalter_id`);

--
-- Indizes für die Tabelle `miete_konto`
--
ALTER TABLE `miete_konto`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uniq_miete_konto` (`mietervertrag_id`,`type`,`period`,`source_table`,`source_id`);

--
-- Indizes für die Tabelle `sachkonten`
--
ALTER TABLE `sachkonten`
  ADD PRIMARY KEY (`id`),
  ADD KEY `liegenschaft_id` (`liegenschaft_id`),
  ADD KEY `einheit_id` (`einheit_id`),
  ADD KEY `idx_sachkonten_liegenschaft_anmerkung` (`liegenschaft_id`,`anmerkung`);

--
-- Indizes für die Tabelle `settings`
--
ALTER TABLE `settings`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Indizes für die Tabelle `todos`
--
ALTER TABLE `todos`
  ADD PRIMARY KEY (`id`);

--
-- Indizes für die Tabelle `verwalter`
--
ALTER TABLE `verwalter`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `liegenschaft_id` (`liegenschaft_id`),
  ADD UNIQUE KEY `einheit_id` (`einheit_id`);

--
-- Indizes für die Tabelle `zaehler`
--
ALTER TABLE `zaehler`
  ADD PRIMARY KEY (`id`),
  ADD KEY `fk_zaehler_liegenschaft` (`liegenschaft_id`),
  ADD KEY `fk_zaehler_einheit` (`einheit_id`);

--
-- Indizes für die Tabelle `zaehlerstaende`
--
ALTER TABLE `zaehlerstaende`
  ADD PRIMARY KEY (`id`),
  ADD KEY `fk_zahelerstaende_zaehler` (`zaehler_id`);

--
-- AUTO_INCREMENT für exportierte Tabellen
--

--
-- AUTO_INCREMENT für Tabelle `auszuege`
--
ALTER TABLE `auszuege`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=536;

--
-- AUTO_INCREMENT für Tabelle `bank_imports`
--
ALTER TABLE `bank_imports`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=69;

--
-- AUTO_INCREMENT für Tabelle `buchungen`
--
ALTER TABLE `buchungen`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=598;

--
-- AUTO_INCREMENT für Tabelle `dateien`
--
ALTER TABLE `dateien`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=100;

--
-- AUTO_INCREMENT für Tabelle `eigentuemer`
--
ALTER TABLE `eigentuemer`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- AUTO_INCREMENT für Tabelle `einheiten`
--
ALTER TABLE `einheiten`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=15;

--
-- AUTO_INCREMENT für Tabelle `journal`
--
ALTER TABLE `journal`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=7;

--
-- AUTO_INCREMENT für Tabelle `liegenschaften`
--
ALTER TABLE `liegenschaften`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=6;

--
-- AUTO_INCREMENT für Tabelle `mieter`
--
ALTER TABLE `mieter`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=26;

--
-- AUTO_INCREMENT für Tabelle `mietervertrag`
--
ALTER TABLE `mietervertrag`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=13;

--
-- AUTO_INCREMENT für Tabelle `miete_konto`
--
ALTER TABLE `miete_konto`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=212;

--
-- AUTO_INCREMENT für Tabelle `sachkonten`
--
ALTER TABLE `sachkonten`
  MODIFY `id` int(10) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=28;

--
-- AUTO_INCREMENT für Tabelle `settings`
--
ALTER TABLE `settings`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=9;

--
-- AUTO_INCREMENT für Tabelle `todos`
--
ALTER TABLE `todos`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=13;

--
-- AUTO_INCREMENT für Tabelle `verwalter`
--
ALTER TABLE `verwalter`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT für Tabelle `zaehler`
--
ALTER TABLE `zaehler`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=29;

--
-- AUTO_INCREMENT für Tabelle `zaehlerstaende`
--
ALTER TABLE `zaehlerstaende`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=83;

--
-- Constraints der exportierten Tabellen
--

--
-- Constraints der Tabelle `buchungen`
--
ALTER TABLE `buchungen`
  ADD CONSTRAINT `buchungen_ibfk_1` FOREIGN KEY (`einheit_id`) REFERENCES `einheiten` (`id`),
  ADD CONSTRAINT `buchungen_ibfk_2` FOREIGN KEY (`liegenschaft_id`) REFERENCES `liegenschaften` (`id`),
  ADD CONSTRAINT `buchungen_ibfk_3` FOREIGN KEY (`sachkonto_id`) REFERENCES `sachkonten` (`id`);

--
-- Constraints der Tabelle `einheiten`
--
ALTER TABLE `einheiten`
  ADD CONSTRAINT `fk_einheiten_liegenschaften` FOREIGN KEY (`liegenschaft_id`) REFERENCES `liegenschaften` (`id`) ON DELETE SET NULL ON UPDATE CASCADE;

--
-- Constraints der Tabelle `journal`
--
ALTER TABLE `journal`
  ADD CONSTRAINT `fk_journal_mieter` FOREIGN KEY (`mieter_id`) REFERENCES `mieter` (`id`) ON DELETE SET NULL;

--
-- Constraints der Tabelle `liegenschaften`
--
ALTER TABLE `liegenschaften`
  ADD CONSTRAINT `fk_lieg_eigentuemer1` FOREIGN KEY (`eigentuemer1_id`) REFERENCES `eigentuemer` (`id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_lieg_eigentuemer2` FOREIGN KEY (`eigentuemer2_id`) REFERENCES `eigentuemer` (`id`) ON DELETE SET NULL;

--
-- Constraints der Tabelle `mietervertrag`
--
ALTER TABLE `mietervertrag`
  ADD CONSTRAINT `fk_mietervertrag_mieter2` FOREIGN KEY (`mieter2_id`) REFERENCES `mieter` (`id`),
  ADD CONSTRAINT `fk_mietervertrag_verwalter` FOREIGN KEY (`verwalter_id`) REFERENCES `verwalter` (`id`) ON DELETE SET NULL,
  ADD CONSTRAINT `mietervertrag_ibfk_1` FOREIGN KEY (`mieter_id`) REFERENCES `mieter` (`id`),
  ADD CONSTRAINT `mietervertrag_ibfk_2` FOREIGN KEY (`einheit_id`) REFERENCES `einheiten` (`id`) ON DELETE SET NULL;

--
-- Constraints der Tabelle `miete_konto`
--
ALTER TABLE `miete_konto`
  ADD CONSTRAINT `fk_miete_konto_vertrag` FOREIGN KEY (`mietervertrag_id`) REFERENCES `mietervertrag` (`id`);

--
-- Constraints der Tabelle `sachkonten`
--
ALTER TABLE `sachkonten`
  ADD CONSTRAINT `fk_sachkonten_einheit` FOREIGN KEY (`einheit_id`) REFERENCES `einheiten` (`id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_sachkonten_liegenschaft` FOREIGN KEY (`liegenschaft_id`) REFERENCES `liegenschaften` (`id`) ON DELETE SET NULL;

--
-- Constraints der Tabelle `verwalter`
--
ALTER TABLE `verwalter`
  ADD CONSTRAINT `fk_verwalter_einheit` FOREIGN KEY (`einheit_id`) REFERENCES `einheiten` (`id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_verwalter_liegenschaft` FOREIGN KEY (`liegenschaft_id`) REFERENCES `liegenschaften` (`id`) ON DELETE SET NULL;

--
-- Constraints der Tabelle `zaehler`
--
ALTER TABLE `zaehler`
  ADD CONSTRAINT `fk_zaehler_einheit` FOREIGN KEY (`einheit_id`) REFERENCES `einheiten` (`id`),
  ADD CONSTRAINT `fk_zaehler_liegenschaft` FOREIGN KEY (`liegenschaft_id`) REFERENCES `liegenschaften` (`id`);

--
-- Constraints der Tabelle `zaehlerstaende`
--
ALTER TABLE `zaehlerstaende`
  ADD CONSTRAINT `fk_zahelerstaende_zaehler` FOREIGN KEY (`zaehler_id`) REFERENCES `zaehler` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
