from threading import Timer


class Scheduler(Timer):
    def __init__(self, name, interval, function, args):
        Timer.__init__(self, interval, function, args)
        self.name = name
        self.daemon = True
