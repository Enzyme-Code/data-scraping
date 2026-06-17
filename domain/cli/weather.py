from domain.weather.pipelines.general_36hour.update import update as update_36
from domain.weather.pipelines.three_days.update import update as update_three_day
from domain.weather.pipelines.one_week.update import update as update_one_week


def run():
    update_36()
    update_three_day()
    update_one_week()

    
if __name__ == "__main__":
    run()