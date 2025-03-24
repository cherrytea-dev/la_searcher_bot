class Search:
    def __init__(self, topic_id=None):
        self.topic_id = topic_id


class PercentGroup:
    def __init__(
        self,
        n=None,
        start_percent=None,
        finish_percent=None,
        start_num=None,
        finish_num=None,
        frequency=None,
        first_delay=None,
        searches=None,  # noqa
    ):
        searches = []
        self.n = n
        self.sp = start_percent
        self.fp = finish_percent
        self.sn = start_num
        self.fn = finish_num
        self.f = frequency
        self.d = first_delay
        self.s = searches

    def __str__(self):
        days = f' or {int(self.f // 1440)} day(s)' if self.f >= 1440 else ''
        return (
            f'N{self.n: <2}: {self.sp}%–{self.fp}%. Updated every {self.f} minute(s){days}. '
            f'First delay = {self.d} minutes. nums {self.sn}-{self.fn}. num of searches {len(self.s)}'
        )
