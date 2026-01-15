from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
import uuid

# --- GERENCIADOR DE USUÁRIO ---

class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('O número de telefone deve ser fornecido')
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(phone_number, password, **extra_fields)

# --- MODELO DE USUÁRIO ---

class CustomUser(AbstractBaseUser, PermissionsMixin):
    phone_number = models.CharField(max_length=20, unique=True, verbose_name="Número de Telefone")
    full_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nome Completo")
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    invite_code = models.CharField(max_length=8, unique=True, blank=True, null=True)
    invited_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Convidado por")
    available_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Saldo Disponível")
    subsidy_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Saldo de Subsídios")
    level_active = models.BooleanField(default=False, verbose_name="Nível Ativo")
    roulette_spins = models.IntegerField(default=0, verbose_name="Giros da Roleta")
    is_free_plan_used = models.BooleanField(default=False, verbose_name="Plano Gratuito Ativado")

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.phone_number

    def save(self, *args, **kwargs):
        if not self.invite_code:
            while True:
                new_invite_code = uuid.uuid4().hex[:8].upper()
                if not CustomUser.objects.filter(invite_code=new_invite_code).exists():
                    self.invite_code = new_invite_code
                    break
        super().save(*args, **kwargs)

# --- CONFIGURAÇÕES E BANCOS ---

class PlatformSettings(models.Model):
    whatsapp_link = models.URLField(verbose_name="Link do WhatsApp", help_text="Link para suporte.")
    history_text = models.TextField(verbose_name="Texto 'Sobre'")
    deposit_instruction = models.TextField(verbose_name="Instrução Depósito")
    withdrawal_instruction = models.TextField(verbose_name="Instrução Saque")
    
    class Meta:
        verbose_name = "Configuração da Plataforma"
        verbose_name_plural = "Configurações da Plataforma"

class PlatformBankDetails(models.Model):
    bank_name = models.CharField(max_length=100, verbose_name="Nome do Banco/Rede")
    IBAN = models.CharField(max_length=100, verbose_name="IBAN / Chave PIX / Carteira")
    account_holder_name = models.CharField(max_length=100, verbose_name="Titular")

    class Meta:
        verbose_name = "Conta da Plataforma"
        verbose_name_plural = "Contas da Plataforma"

class BankDetails(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="bank_details")
    bank_name = models.CharField(max_length=100, verbose_name="Banco")
    IBAN = models.CharField(max_length=100, verbose_name="IBAN / Chave PIX")
    account_holder_name = models.CharField(max_length=100, verbose_name="Titular")

    class Meta:
        verbose_name = "Dados Bancários do Usuário"
        verbose_name_plural = "Dados Bancários dos Usuários"

# --- FLUXO FINANCEIRO ---

class Deposit(models.Model):
    PAYMENT_METHODS = [
        ('bank', 'Banco (Angola)'),
        ('pix', 'PIX (Brasil)'),
        ('trc20', 'Cripto (USDT TRC20)'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name="Usuário")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Valor")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default='bank', verbose_name="Método")
    payer_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nome/ID do Comprovativo")
    proof_of_payment = models.ImageField(upload_to='deposit_proofs/', verbose_name="Comprovativo")
    is_approved = models.BooleanField(default=False, verbose_name="Aprovado")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data")
    
    class Meta:
        verbose_name = "Depósito"
        verbose_name_plural = "Depósitos"

    def __str__(self):
        return f"{self.user.phone_number} - {self.amount} ({self.get_payment_method_display()})"

class Withdrawal(models.Model):
    STATUS_CHOICES = [
        ('Pendente', 'Pendente'),
        ('Aprovado', 'Aprovado'),
        ('Recusado', 'Recusado'),
    ]
    
    # Adicionado suporte a múltiplos métodos no saque
    WITHDRAWAL_METHODS = [
        ('bank', 'Banco (IBAN)'),
        ('pix', 'PIX'),
        ('usdt', 'USDT (TRC20)'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name="Usuário")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Valor")
    method = models.CharField(max_length=10, choices=WITHDRAWAL_METHODS, default='bank', verbose_name="Método Escolhido")
    withdrawal_details = models.TextField(blank=True, null=True, verbose_name="Dados do Recebimento", help_text="Ex: IBAN ou Chave PIX usada no momento do saque")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pendente', verbose_name="Status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data de Solicitação")

    class Meta:
        verbose_name = "Saque"
        verbose_name_plural = "Saques"

    def __str__(self):
        return f"{self.user.phone_number} - {self.amount} ({self.status})"

# --- NÍVEIS E TAREFAS ---

class Level(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Nome do Nível")
    deposit_value = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Custo de Ativação")
    daily_gain = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Ganho Diário")
    monthly_gain = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Ganho Mensal")
    cycle_days = models.IntegerField(verbose_name="Dias de Ciclo")
    image = models.ImageField(upload_to='level_images/', verbose_name="Ícone/Imagem")

    def __str__(self):
        return self.name

class UserLevel(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    level = models.ForeignKey(Level, on_delete=models.CASCADE)
    purchase_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

class Task(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    earnings = models.DecimalField(max_digits=12, decimal_places=2)
    completed_at = models.DateTimeField(auto_now_add=True)

# --- ROLETA ---

class Roulette(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    prize = models.DecimalField(max_digits=12, decimal_places=2)
    spin_date = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=True)

class RouletteSettings(models.Model):
    prizes = models.CharField(max_length=255, help_text="Lista de prêmios separados por vírgula. Ex: 0,500,1000,5000")

    class Meta:
        verbose_name = "Configuração da Roleta"
        verbose_name_plural = "Configurações da Roleta"
        