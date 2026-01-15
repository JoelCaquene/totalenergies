from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import random
from datetime import date, time, datetime
from django.utils import timezone
from decimal import Decimal

from .forms import RegisterForm, DepositForm, WithdrawalForm, BankDetailsForm
from .models import PlatformSettings, CustomUser, Level, UserLevel, BankDetails, Deposit, Withdrawal, Task, PlatformBankDetails, Roulette, RouletteSettings

# --- FUNÇÃO HOME ---
def home(request):
    if request.user.is_authenticated:
        return redirect('menu')
    else:
        return redirect('cadastro')

# --- FUNÇÃO MENU ---
@login_required
def menu(request):
    user = request.user
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()
    approved_deposit_total = Deposit.objects.filter(user=user, is_approved=True).aggregate(Sum('amount'))['amount__sum'] or 0
    today = date.today()
    daily_income = Task.objects.filter(user=user, completed_at__date=today).aggregate(Sum('earnings'))['earnings__sum'] or 0
    total_withdrawals = Withdrawal.objects.filter(user=user, status='Aprovado').aggregate(Sum('amount'))['amount__sum'] or 0

    try:
        platform_settings = PlatformSettings.objects.first()
        whatsapp_link = platform_settings.whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'

    context = {
        'user': user,
        'active_level': active_level,
        'approved_deposit_total': approved_deposit_total,
        'daily_income': daily_income,
        'total_withdrawals': total_withdrawals,
        'whatsapp_link': whatsapp_link,
    }
    return render(request, 'menu.html', context)

# --- CADASTRO ---
def cadastro(request):
    invite_code_from_url = request.GET.get('invite', None)
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.available_balance = 0 
            
            invited_by_code = form.cleaned_data.get('invited_by_code')
            if invited_by_code:
                try:
                    invited_by_user = CustomUser.objects.get(invite_code=invited_by_code)
                    user.invited_by = invited_by_user
                except CustomUser.DoesNotExist:
                    messages.error(request, 'Código de convite inválido.')
                    return render(request, 'cadastro.html', {'form': form})
            
            user.save()
            login(request, user)
            messages.success(request, 'Cadastro realizado com sucesso!')
            return redirect('menu')
    else:
        form = RegisterForm(initial={'invited_by_code': invite_code_from_url}) if invite_code_from_url else RegisterForm()
    
    try:
        whatsapp_link = PlatformSettings.objects.first().whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'
    return render(request, 'cadastro.html', {'form': form, 'whatsapp_link': whatsapp_link})

def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('menu')
    else:
        form = AuthenticationForm()
    try:
        whatsapp_link = PlatformSettings.objects.first().whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'
    return render(request, 'login.html', {'form': form, 'whatsapp_link': whatsapp_link})

@login_required
def user_logout(request):
    logout(request)
    return redirect('menu')

# --- DEPÓSITO (ATUALIZADO COM MULTI-MÉTODOS) ---
@login_required
def deposito(request):
    platform_bank_details = PlatformBankDetails.objects.all()
    platform_settings = PlatformSettings.objects.first()
    deposit_instruction = platform_settings.deposit_instruction if platform_settings else 'Instruções não disponíveis.'
    
    level_deposits = Level.objects.all().values_list('deposit_value', flat=True).distinct().order_by('deposit_value')
    level_deposits_list = [str(d) for d in level_deposits] 

    if request.method == 'POST':
        form = DepositForm(request.POST, request.FILES)
        payment_method = request.POST.get('payment_method', 'bank')
        payer_name = request.POST.get('payer_name', '')

        if form.is_valid():
            deposit = form.save(commit=False)
            deposit.user = request.user
            deposit.payment_method = payment_method
            deposit.payer_name = payer_name
            deposit.save()
            
            return render(request, 'deposito.html', {
                'platform_bank_details': platform_bank_details,
                'deposit_instruction': deposit_instruction,
                'level_deposits_list': level_deposits_list,
                'deposit_success': True 
            })
        else:
            messages.error(request, 'Erro ao enviar o depósito. Verifique os campos.')
    
    form = DepositForm()
    context = {
        'platform_bank_details': platform_bank_details,
        'deposit_instruction': deposit_instruction,
        'form': form,
        'level_deposits_list': level_deposits_list,
        'deposit_success': False,
    }
    return render(request, 'deposito.html', context)

@login_required
def approve_deposit(request, deposit_id):
    if not request.user.is_staff:
        return redirect('menu')
    deposit = get_object_or_404(Deposit, id=deposit_id)
    if not deposit.is_approved:
        deposit.is_approved = True
        deposit.save()
        
        deposit.user.available_balance += deposit.amount
        deposit.user.save()
        messages.success(request, f'Depósito de {deposit.amount} aprovado para {deposit.user.phone_number}.')
    return redirect('renda')

# --- SAQUE (ATUALIZADO COM ESCOLHA DE MÉTODO) ---
@login_required
def saque(request):
    MIN_WITHDRAWAL_AMOUNT = 2500
    START_TIME = time(9, 0, 0)
    END_TIME = time(17, 0, 0)
    
    platform_settings = PlatformSettings.objects.first()
    withdrawal_instruction = platform_settings.withdrawal_instruction if platform_settings else ''
    withdrawal_records = Withdrawal.objects.filter(user=request.user).order_by('-created_at')
    
    now = timezone.localtime(timezone.now()).time()
    today = timezone.localdate(timezone.now())
    is_time_to_withdraw = START_TIME <= now <= END_TIME
    
    withdrawals_today_count = Withdrawal.objects.filter(
        user=request.user, 
        created_at__date=today, 
        status__in=['Pendente', 'Aprovado']
    ).count()
    can_withdraw_today = withdrawals_today_count == 0
    
    if request.method == 'POST':
        form = WithdrawalForm(request.POST)
        # Captura o método e dados adicionais do formulário
        metodo_escolhido = request.POST.get('withdrawal_method')
        
        if form.is_valid():
            amount = form.cleaned_data['amount']
            
            if not metodo_escolhido:
                messages.error(request, 'Selecione um método de levantamento.')
            elif not can_withdraw_today:
                messages.error(request, 'Apenas 1 saque por dia.')
            elif not is_time_to_withdraw:
                messages.error(request, 'Horário de saque: 09:00 às 17:00.')
            elif amount < MIN_WITHDRAWAL_AMOUNT:
                messages.error(request, f'O valor mínimo é {MIN_WITHDRAWAL_AMOUNT} Kz.')
            elif request.user.available_balance < amount:
                messages.error(request, 'Saldo insuficiente.')
            else:
                # Cria o saque salvando o método nos detalhes (ou campo específico se existir no model)
                withdrawal = Withdrawal.objects.create(
                    user=request.user, 
                    amount=amount,
                )
                
                # Opcional: Salvar detalhes extras se o seu model tiver um campo 'payment_details'
                # withdrawal.payment_method = metodo_escolhido
                # withdrawal.save()

                request.user.available_balance -= amount
                request.user.save()
                messages.success(request, f'Pedido de saque via {metodo_escolhido} enviado com sucesso.')
                return redirect('saque')
    else:
        form = WithdrawalForm()

    context = {
        'withdrawal_instruction': withdrawal_instruction,
        'withdrawal_records': withdrawal_records,
        'form': form,
        'is_time_to_withdraw': is_time_to_withdraw,
        'MIN_WITHDRAWAL_AMOUNT': MIN_WITHDRAWAL_AMOUNT,
        'can_withdraw_today': can_withdraw_today,
    }
    return render(request, 'saque.html', context)

# --- TAREFAS ---
@login_required
def tarefa(request):
    user = request.user
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()
    is_estagiario = active_level is None
    today = timezone.localdate()
    tasks_completed_today = Task.objects.filter(user=user, completed_at__date=today).count()
    
    context = {
        'is_estagiario': is_estagiario,
        'active_level': active_level,
        'tasks_completed_today': tasks_completed_today,
        'max_tasks': 1,
    }
    return render(request, 'tarefa.html', context)

@login_required
@require_POST
def process_task(request):
    user = request.user
    today = timezone.localdate()

    if Task.objects.filter(user=user, completed_at__date=today).exists():
        return JsonResponse({'success': False, 'message': 'Limite diário de tarefas alcançado.'})

    try:
        active_user_level = UserLevel.objects.filter(user=user, is_active=True).select_related('level').first()

        if active_user_level:
            task_earnings = Decimal(str(active_user_level.level.daily_gain))
        else:
            task_earnings = Decimal('80.00')

        Task.objects.create(user=user, earnings=task_earnings) 
        user.available_balance += task_earnings
        user.save()

        p1 = user.invited_by
        if p1:
            subsidy_a = task_earnings * Decimal('0.20')
            p1.available_balance += subsidy_a
            p1.subsidy_balance += subsidy_a
            p1.save()

            p2 = p1.invited_by
            if p2:
                subsidy_b = task_earnings * Decimal('0.03')
                p2.available_balance += subsidy_b
                p2.subsidy_balance += subsidy_b
                p2.save()

                p3 = p2.invited_by
                if p3:
                    subsidy_c = task_earnings * Decimal('0.02')
                    p3.available_balance += subsidy_c
                    p3.subsidy_balance += subsidy_c
                    p3.save()

        return JsonResponse({
            'success': True, 
            'message': f'Tarefa concluída! {task_earnings} KZ adicionados ao saldo.'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro: {str(e)}'})

# --- NÍVEIS VIP ---
@login_required
def nivel(request):
    if request.method == 'POST':
        level_id = request.POST.get('level_id')
        level_to_buy = get_object_or_404(Level, id=level_id)
        val = level_to_buy.deposit_value

        user_levels = UserLevel.objects.filter(user=request.user, is_active=True).values_list('level__id', flat=True)
        if level_to_buy.id in user_levels:
            messages.error(request, 'Você já possui este nível ativo.')
            return redirect('nivel')

        if request.user.available_balance >= val:
            request.user.available_balance -= val
            UserLevel.objects.create(user=request.user, level=level_to_buy, is_active=True)
            request.user.level_active = True
            request.user.save()

            p1 = request.user.invited_by
            if p1 and UserLevel.objects.filter(user=p1, is_active=True).exists():
                com1 = val * Decimal('0.15')
                p1.available_balance += com1
                p1.subsidy_balance += com1
                p1.save()

                p2 = p1.invited_by
                if p2 and UserLevel.objects.filter(user=p2, is_active=True).exists():
                    com2 = val * Decimal('0.03')
                    p2.available_balance += com2
                    p2.subsidy_balance += com2
                    p2.save()

                    p3 = p2.invited_by
                    if p3 and UserLevel.objects.filter(user=p3, is_active=True).exists():
                        com3 = val * Decimal('0.01')
                        p3.available_balance += com3
                        p3.subsidy_balance += com3
                        p3.save()

            messages.success(request, f'Parabéns! Nível {level_to_buy.name} ativado com sucesso!')
        else:
            messages.error(request, 'Saldo insuficiente para ativar este nível.')
        return redirect('nivel')
    
    context = {
        'levels': Level.objects.all().order_by('deposit_value'),
        'user_levels': UserLevel.objects.filter(user=request.user, is_active=True).values_list('level__id', flat=True),
    }
    return render(request, 'nivel.html', context)

# --- EQUIPA ---
@login_required
def equipa(request):
    user = request.user
    level_a = CustomUser.objects.filter(invited_by=user)
    level_b = CustomUser.objects.filter(invited_by__in=level_a)
    level_c = CustomUser.objects.filter(invited_by__in=level_b)

    context = {
        'team_count': level_a.count() + level_b.count() + level_c.count(),
        'total_investors': (level_a.filter(userlevel__is_active=True).distinct().count() + 
                           level_b.filter(userlevel__is_active=True).distinct().count() + 
                           level_c.filter(userlevel__is_active=True).distinct().count()),
        'invite_link': request.build_absolute_uri(reverse('cadastro')) + f'?invite={user.invite_code}',
        'subsidy_balance': user.subsidy_balance,
        'level_a_count': level_a.count(),
        'level_a_investors': level_a.filter(userlevel__is_active=True).distinct().count(),
        'level_b_count': level_b.count(),
        'level_b_investors': level_b.filter(userlevel__is_active=True).distinct().count(),
        'level_c_count': level_c.count(),
        'level_c_investors': level_c.filter(userlevel__is_active=True).distinct().count(),
        'level_a': level_a,
        'level_b': level_b,
        'level_c': level_c,
    }
    return render(request, 'equipa.html', context)

# --- ROLETA ---
@login_required
def roleta(request):
    user = request.user
    roulette_settings = RouletteSettings.objects.first()
    prizes_list = [p.strip() for p in roulette_settings.prizes.split(',')] if roulette_settings and roulette_settings.prizes else ['0', '500', '1000', '0', '5000', '200', '0', '10000']
    recent_winners = Roulette.objects.filter(is_approved=True).order_by('-spin_date')[:10]
    context = {'roulette_spins': user.roulette_spins, 'prizes_list': prizes_list, 'recent_winners': recent_winners}
    return render(request, 'roleta.html', context)

@login_required
@require_POST
def spin_roulette(request):
    user = request.user
    if not user.roulette_spins or user.roulette_spins <= 0:
        return JsonResponse({'success': False, 'message': 'Sem giros disponíveis.'})

    roulette_settings = RouletteSettings.objects.first()
    prizes_raw = [p.strip() for p in roulette_settings.prizes.split(',')] if roulette_settings and roulette_settings.prizes else ['0', '500', '1000', '0', '5000', '200', '0', '10000']
    
    weighted_pool = []
    for p in prizes_raw:
        val = Decimal(p)
        if val == 0: weighted_pool.extend([p] * 10)
        elif val <= 500: weighted_pool.extend([p] * 5)
        else: weighted_pool.append(p)

    winning_prize_str = random.choice(weighted_pool)
    prize_amount = Decimal(winning_prize_str)
    
    user.roulette_spins -= 1
    user.subsidy_balance += prize_amount
    user.available_balance += prize_amount
    user.save()
    
    Roulette.objects.create(user=user, prize=prize_amount, is_approved=True)

    return JsonResponse({
        'success': True, 
        'prize': winning_prize_str, 
        'remaining_spins': user.roulette_spins
    })

# --- SOBRE E PERFIL ---
@login_required
def sobre(request):
    platform_settings = PlatformSettings.objects.first()
    history_text = platform_settings.history_text if platform_settings else 'Informação indisponível.'
    return render(request, 'sobre.html', {'history_text': history_text})

@login_required
def perfil(request):
    bank_details, created = BankDetails.objects.get_or_create(user=request.user)
    withdrawal_records = Withdrawal.objects.filter(user=request.user).order_by('-created_at')
    
    if request.method == 'POST':
        if 'update_bank' in request.POST:
            form = BankDetailsForm(request.POST, instance=bank_details)
            if form.is_valid():
                form.save()
                messages.success(request, 'Dados bancários atualizados com sucesso!')
                return redirect('perfil')
        
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Senha alterada com sucesso!')
                return redirect('perfil')

    context = {
        'form': BankDetailsForm(instance=bank_details),
        'bank_info': bank_details,
        'password_form': PasswordChangeForm(request.user),
        'user_levels': UserLevel.objects.filter(user=request.user, is_active=True),
        'withdrawal_records': withdrawal_records,
    }
    return render(request, 'perfil.html', context)

@login_required
def renda(request):
    user = request.user
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()
    approved_deposit_total = Deposit.objects.filter(user=user, is_approved=True).aggregate(Sum('amount'))['amount__sum'] or 0
    today = date.today()
    daily_income = Task.objects.filter(user=user, completed_at__date=today).aggregate(Sum('earnings'))['earnings__sum'] or 0
    total_withdrawals = Withdrawal.objects.filter(user=user, status='Aprovado').aggregate(Sum('amount'))['amount__sum'] or 0
    total_income = (Task.objects.filter(user=user).aggregate(Sum('earnings'))['earnings__sum'] or 0) + user.subsidy_balance
    
    context = {
        'user': user,
        'active_level': active_level,
        'approved_deposit_total': approved_deposit_total,
        'daily_income': daily_income,
        'total_withdrawals': total_withdrawals,
        'total_income': total_income,
    }
    return render(request, 'renda.html', context)
    