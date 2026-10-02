pool, (master, storekeeper, procurement, accounting) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Мастер участка', 'Кладовщик', 'Отдел снабжения', 'Бухгалтерия'])

demand = DIAGRAM.add_user_task('Сформировать потребность в материалах', master)
check = DIAGRAM.add_user_task('Проверить остатки', storekeeper)
decision = DIAGRAM.add_exclusive_gateway('Материал в наличии?', storekeeper)

give_now = DIAGRAM.add_user_task('Выдать материал мастеру', storekeeper)

request = DIAGRAM.add_user_task('Запросить коммерческие предложения', procurement)
select = DIAGRAM.add_user_task('Выбрать поставщика', procurement)
contract = DIAGRAM.add_user_task('Заключить договор', procurement)
pay = DIAGRAM.add_user_task('Оплатить счёт', accounting)
supply = DIAGRAM.add_user_task('Поставить материалы', storekeeper)
receive = DIAGRAM.add_user_task('Принять материалы по накладной', storekeeper)
give_later = DIAGRAM.add_user_task('Выдать материал мастеру', storekeeper)

sign = DIAGRAM.add_user_task('Подписать требование-накладную', master)

DIAGRAM.add_link(ROOT_START_TASK_ID, demand)
DIAGRAM.add_link(demand, check)
DIAGRAM.add_link(check, decision)
DIAGRAM.add_link(decision, give_now, name='да')
DIAGRAM.add_link(decision, request, name='нет')
DIAGRAM.add_link(give_now, sign)

DIAGRAM.add_link(request, select)
DIAGRAM.add_link(select, contract)
DIAGRAM.add_link(contract, pay)
DIAGRAM.add_link(pay, supply)
DIAGRAM.add_link(supply, receive)
DIAGRAM.add_link(receive, give_later)
DIAGRAM.add_link(give_later, sign)

DIAGRAM.add_link(sign, ROOT_END_TASK_ID)