# coding: utf-8
from __future__ import unicode_literals
from datetime import datetime, timedelta, time
from collections import OrderedDict
import re
import unittest
import copy


# Order matters: long names should come first in regex
WEEKDAYS = OrderedDict([
    ('понедельник', 1),
    ('пн', 1),
    ('вторник', 2),
    ('вт', 2),
    ('среда', 3),
    ('ср', 3),
    ('четверг', 4),
    ('чт', 4),
    ('пятница', 5),
    ('пт', 5),
    ('суббота', 6),
    ('сб', 6),
    ('воскресенье', 7),
    ('воскр', 7),
    ('вс', 7),
])

WEEKDAY_RANGES = {
    'будни': (1, 5),
    'без перерыва и выходных': (1, 7),
    'выходные': (6, 7),
    'ежедневно': (1, 7),
    'ежеднено': (1, 7),
    'режим работы': (1, 7),
}


def build_regex():
    """Return regex string with groups of token types."""
    final_pattern = []

    # Hour '19:00' or '19.00' or '19-00' or '19'
    hour_pattern_string = r'(?P<hour>\d{1,2}[:.-]\d{2}|\d{1,2})'
    final_pattern.append(hour_pattern_string)

    # Weekdays, i.e. 'пн' or 'суббота'
    weekday_pattern_string = r'(?P<weekday>' + '|'.join(WEEKDAYS.keys()) + ')'
    final_pattern.append(weekday_pattern_string)

    # Weekday ranges like 'будни'
    weekday_range_pattern_string = r'(?P<weekday_range>' + '|'.join(WEEKDAY_RANGES.keys()) + ')'
    final_pattern.append(weekday_range_pattern_string)

    # Any '-' or 'до' or ',' as a range qualifier
    range_mark_pattern_string = r'(?P<range_mark>-|до|,)'
    final_pattern.append(range_mark_pattern_string)

    #  Any alphanumeric sequence of characters or underscore
    other_word_pattern_string = r'(?P<word>\w+)'
    final_pattern.append(other_word_pattern_string)
    return '|'.join(final_pattern)

token_pattern = re.compile(build_regex(), re.UNICODE | re.IGNORECASE)


class WorkingHours(object):
    """Extract working hours from the text provided."""

    def __init__(self, text):
        self._raw_schedule = OrderedDict([(weekday_number, None) for weekday_number in set(WEEKDAYS.values())])
        self.schedule = None
        ranges = Parser(text).parse()
        for dayhours_range_pair in ranges:
            days_range = dayhours_range_pair[0]
            hours_range = dayhours_range_pair[1]
            if days_range:
                for day in range(days_range.start, days_range.end + 1):
                    self._raw_schedule[day] = hours_range
            elif hours_range:
                # If only hours part, then we apply this part for all days
                for day in self._raw_schedule.keys():
                    self._raw_schedule[day] = hours_range
            else:
                raise ValueError

    def check_working_time(self, datetime_obj=datetime.now()):
        hours_range = self._raw_schedule[datetime_obj.isoweekday()]
        if hours_range is None:
            return False
        start_datetime = self.parse_hours(hours_range.start, datetime_obj)
        end_datetime = self.parse_hours(hours_range.end, datetime_obj)
        if start_datetime and end_datetime:
            return start_datetime <= datetime_obj < end_datetime
        else:
            # Safe default
            return True

    def get_next_working_day(self, datetime_obj):
        """
        Next working day in iso format, i.e. an integer from 1 to 7,
        or None in case of no working days available.
        """
        current_day = datetime_obj.isoweekday()
        next_day = current_day % 7 + 1
        while next_day != current_day:
            hours = self._raw_schedule[next_day]
            if hours:
                return next_day
            next_day = next_day % 7 + 1
        return None

    def get_next_working_hours(self, datetime_obj=datetime.now()):
        next_working_day = self.get_next_working_day(datetime_obj)
        start_datetime = end_datetime = None
        if next_working_day:
            next_date = datetime(datetime_obj.year, datetime_obj.month, 
                                 datetime_obj.day)
		    # Modular subtraction
            delta = ((next_working_day + 7) - datetime_obj.isoweekday()) % 7
            next_date += timedelta(days=delta)
            if next_working_day:
                hours_range = self._raw_schedule[next_working_day]
                if hours_range:
                    start_datetime = self.parse_hours(hours_range.start, next_date)
                    end_datetime = self.parse_hours(hours_range.end, next_date)
        return start_datetime, end_datetime

    def build_schedule(self):
        """
        Transform Range hours objects to tuples of time objects.
        Example of returned schedule for the text 'Пн-Пт: 9.00-19.00':
            {1: (datetime.time(9, 0), datetime.time(19, 0)),
            2: (datetime.time(9, 0), datetime.time(19, 0)),
            3: (datetime.time(9, 0), datetime.time(19, 0)),
            4: (datetime.time(9, 0), datetime.time(19, 0)),
            5: (datetime.time(9, 0), datetime.time(19, 0)),
            6: None,
            7: None}

        """
        schedule = OrderedDict()
        for weekday in self._raw_schedule.keys():
            hours_range = self._raw_schedule[weekday]
            time_obj = time()
            if hours_range:
                start_datetime = self.parse_hours(hours_range.start, time_obj)
                end_datetime = self.parse_hours(hours_range.end, time_obj)
                schedule[weekday] = (start_datetime, end_datetime)
            else:
                schedule[weekday] = None
        return schedule

    def print_schedule(self, format="%H:%M", delimiter="\n",
                       weekend_name="выходной"):
        print_aggregator = []
        weekday_names = {val: key for key, val in WEEKDAYS.items() if len(key) == 2}
        if self.schedule is None:
            self.build_schedule()
        for weekday in self.schedule.keys():
            hours_range = self.schedule[weekday]
            line = [weekday_names.get(weekday, ''), ": "]
            if hours_range is None:
                line.append(weekend_name)
            else:
                start = hours_range[0].strftime(format)
                end = hours_range[1].strftime(format)
                line.extend([start, ' - ', end])
            print_aggregator.append(''.join(line))
        return delimiter.join(print_aggregator)

    @staticmethod
    def parse_hours(hour, datetime_obj):
        hours_datetime = copy.copy(datetime_obj)
        for fmt in ("%H:%M", "%H.%M", "%H-%M",):
            try:
                dummy_datetime = datetime.strptime(hour, fmt)
            except ValueError:
                pass
            else:
                return hours_datetime.replace(hour=dummy_datetime.hour,
                    minute=dummy_datetime.minute, second=0, microsecond=0)
        try:
            dummy_datetime = datetime.strptime(hour, '%H')
        except ValueError:
            pass
        else:
            return hours_datetime.replace(hour=dummy_datetime.hour, minute=0,
                                          second=0, microsecond=0)
        return None


class Token(object):

    """
        Minimal element of parsed text.
        Token types:
        - hour: '19:00' or '19.00' or '19-00' or '19'
        - weekday: 'пн' or 'суббота'
        - weekday_range: 'будни'
        - range_mark: delimiter of weekdays or hours such as '-',
          i.e. second hyphen in 9-00 - 19-00
        - word: any alphanumeric characters and _
    """

    def __init__(self, token_value, token_type):
        self.value = token_value
        self.type = token_type

    def __repr__(self):
        return "{}: {}".format(self.type, self.value)


class Range(object):
    """
        Abstract type for time ranges (days and hours).
    """

    def __init__(self, start, end=None):
        self.start = start
        self.end = end

    def __repr__(self):
        return "{} - {}".format(self.start, self.end)


class Parser(object):

    """
        Parses text with working days and hours.
        Takes into consideration SHOWROOM_WORDS for primary working hours.
    """

    DAYTIME_TOKEN_TYPES = ('hour', 'weekday', 'weekday_range')
    SHOWROOM_WORDS = ('продаж', 'автосалон')
    EXCLUDE_WORDS = ('с', 'c')  # Exclude 'с ... до ...' and English 'c'

    def __init__(self, text):
        self.state = 'OUTSIDE_DATETIME' # Initial state
        # Text preprocessing
        self.text = text.lower().replace('–', '-').replace('—', '-')
        # Tokens iterator
        self._tokens = token_pattern.finditer(self.text)
        self.ranges = []

        # Auxiliary variables to handle day and hour Range objects
        # in INSIDE_DATETIME state
        self.days_range = None
        self.hours_range = None
        self.show_room_flag = False  #

    def get_token(self):
        try:
            match = next(self._tokens)
            for token_type in token_pattern.groupindex.keys():
                token_value = match.group(token_type)
                if token_value:
                    return Token(token_value, token_type)
            raise ValueError("Non-empty match %s without group!" % match)
        except StopIteration:
            return None

    def parse(self):
        """
        Return iterable of tuples (Range(), Range()) 
        where first Range is for days range and second one is for hours Range.
        Example (__repr__ output):
        [(1 - 5, 9-00 - 19-00), (6 - 6, 10-00 - 18-00)]
        """

        token = self.get_token()
        # Finite state machine with two states: INSIDE_DATETIME and OUTSIDE_DATETIME
        # State transitions are listed below
        while token:
            next_token = self.get_token()
            if self.state == 'OUTSIDE_DATETIME' and \
                    token.type in self.DAYTIME_TOKEN_TYPES:
                self.state = 'INSIDE_DATETIME'

            elif self.state == 'INSIDE_DATETIME' and token.type == 'word' and \
                    token.value not in self.EXCLUDE_WORDS:
                self.state = 'OUTSIDE_DATETIME'
                self.save_ranges()
                if self.show_room_flag:
                    break

            elif self.state == 'INSIDE_DATETIME' and token.type == 'range_mark' \
                    and next_token.type not in self.DAYTIME_TOKEN_TYPES:
                self.state = 'OUTSIDE_DATETIME'
                self.save_ranges()
                if self.show_room_flag:
                    break

            elif self.state == 'OUTSIDE_DATETIME' and self.show_room_flag and \
                    token.type not in self.DAYTIME_TOKEN_TYPES and \
                    next_token.type not in self.DAYTIME_TOKEN_TYPES and self.ranges:
                break

            elif self.state == 'INSIDE_DATETIME' and self.hours_range \
                    and self.days_range and token.type in self.DAYTIME_TOKEN_TYPES:
                self.state = 'OUTSIDE_DATETIME'
                self.save_ranges()

            self.handle_state(token, next_token)

            # Exit from INSIDE_DATETIME state
            if next_token is None and self.state == 'INSIDE_DATETIME':
                self.save_ranges()

            token = next_token
        return self.ranges

    def handle_state(self, token, next_token):
        if self.state == 'INSIDE_DATETIME':
            self.handle_datetime_state(token, next_token)
        elif self.state == 'OUTSIDE_DATETIME':
            self.handle_outside_datetime_state(token, next_token)

    def save_ranges(self):
        self.ranges.append((self.days_range, self.hours_range))

        # Clear auxiliary variables for the next INSIDE_DATETIME state
        self.days_range = None
        self.hours_range = None

    def handle_datetime_state(self, token, next_token):
        if token.type == 'hour' and self.hours_range is None:
            self.hours_range = Range(token.value)
        elif token.type == 'weekday' and self.days_range is None:
            self.days_range = Range(WEEKDAYS.get(token.value, None))
            self.days_range.end = WEEKDAYS.get(token.value, None)
        elif token.type == 'weekday_range' and self.days_range is None:
            days_range = WEEKDAY_RANGES.get(token.value, None)
            if days_range:
                self.days_range = Range(days_range[0])
                self.days_range.end = days_range[1]
        elif token.type == 'range_mark' and next_token.type == 'hour' and self.hours_range:
            self.hours_range.end = next_token.value
        elif token.type == 'range_mark' and next_token.type == 'weekday' and self.days_range:
            self.days_range.end = WEEKDAYS.get(next_token.value, None)

    def handle_outside_datetime_state(self, token, next_token):
        if token.value in self.SHOWROOM_WORDS:
            self.show_room_flag = True


class Tests(unittest.TestCase):

    TYPICAL_CASES_WITH_CORRECT_RESULTS = [
        ('Автосалон и сервисный центр: Понедельник - Воскресенье 9:00 - 19:00', 
            '[(1 - 7, 9:00 - 19:00)]', True, False, True),
        ('Автосалон: ежедневно 9:00 - 21:00', 
            '[(1 - 7, 9:00 - 21:00)]', True, False, True),
        ('Сб.:10.00-18.00', '[(6 - 6, 10.00 - 18.00)]', False, False, False),
        ('Пн-Пт: 9.00-19.00', '[(1 - 5, 9.00 - 19.00)]', True, False, False),
        ('Ежедневно с 8.00 до 21.00', 
            '[(1 - 7, 8.00 - 21.00)]', True, False, True),
        ('Пн - Пт.: 10 - 19', '[(1 - 5, 10 - 19)]', True, False, False),
        ('Отдел продаж 09.00 - 21.00 (ежедневно)', 
            '[(1 - 7, 09.00 - 21.00)]', True, False, True),
        ('Пн-Пт: 9-00-19-00 Сб.:10-00 - 18-00', 
            '[(1 - 5, 9-00 - 19-00), (6 - 6, 10-00 - 18-00)]', True, False, False),
        ('Автосалон: пн-пт 09:00-20:00, сб-вс 10:00-19:00 Сервисный центр: ежедневно 08:00-20:00',
         '[(1 - 5, 09:00 - 20:00), (6 - 7, 10:00 - 19:00)]', True, False, True),
        ("""
        - Отдел продаж:
        будни 08:30-20:30,
        выходные 10:00-18:00
        - Отдел сервиса:
        08:30 - 20:30, ежедневно
        - Отдел запчастей:
        08:30 - 20:30, ежедневно
        - Отдел дополнительного оборудования:
         08:30 - 20:30, ежедневно
        """, '[(1 - 5, 08:30 - 20:30), (6 - 7, 10:00 - 18:00)]', True, False, True),
        ('9:00-20:00 без перерыва и выходных', '[(1 - 7, 9:00 - 20:00)]', True, False, True),
        ("""
        Автосалон:
        Пн-пт: 8.00-20.00
        Сб, вс - выходной

        Сервис:
        Пн-сб: 8.00-20.00
        Вс - выходной

        Отдел запчастей:
        Пн-пт: 9.00-19.00
        Сб, вс - выходной
        """, '[(1 - 5, 8.00 - 20.00), (6 - 7, None)]', True, False, False),
        ('9:00-20:00', '[(None, 9:00 - 20:00)]', True, False, True),
        # Long dash test
        ('пн – сб с 8.00 до 22.00; вс с 9.00 до 22.00', 
         '[(1 - 6, 8.00 - 22.00), (7 - 7, 9.00 - 22.00)]', True, False, True)
    ]

    def test_parser(self):
        for case in self.TYPICAL_CASES_WITH_CORRECT_RESULTS:
            ranges = Parser(case[0]).parse()
            self.assertEqual(str(ranges), case[1])

    def test_working_hours(self):
        test_datetime1 = datetime.strptime("23.03.2017 16:00", '%d.%m.%Y %H:%M')  #  Thursday
        test_datetime2 = datetime.strptime("23.03.2017 22:00", '%d.%m.%Y %H:%M')  #  Thursday
        test_datetime3 = datetime.strptime("26.03.2017 16:00", '%d.%m.%Y %H:%M')  #  Sunday
        for case in self.TYPICAL_CASES_WITH_CORRECT_RESULTS:
            self.assertEqual(case[2], WorkingHours(case[0]).check_working_time(test_datetime1))
            self.assertEqual(case[3], WorkingHours(case[0]).check_working_time(test_datetime2))
            self.assertEqual(case[4], WorkingHours(case[0]).check_working_time(test_datetime3))


if __name__ == "__main__":
    unittest.main()
